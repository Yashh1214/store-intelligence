import cv2
import numpy as np
import logging
from typing import Optional, Tuple, Dict, Set
from datetime import datetime
import torch
from torchreid.reid.utils.feature_extractor import FeatureExtractor
from pipeline.topology import StoreTopology, CameraRole

logger = logging.getLogger(__name__)

class GlobalTrack:
    """Represents a unique visitor across all cameras."""
    def __init__(self, global_id: str, embedding: np.ndarray, timestamp: float):
        self.global_id = global_id
        self.embedding = embedding
        self.last_seen = timestamp
        self.last_camera: Optional[str] = None
        self.camera_histories = {}  # cam_id -> list of all historical local track_ids
        self.active_cameras: Set[str] = set()  # cam_id -> currently active on this camera
        
    def update(self, embedding: np.ndarray, timestamp: float, camera_id: str, local_track_id: int):
        # Moving average of embedding to adapt to lighting changes
        self.embedding = 0.8 * self.embedding + 0.2 * embedding
        self.last_seen = max(self.last_seen, timestamp)
        self.last_camera = camera_id
        
        if camera_id not in self.camera_histories:
            self.camera_histories[camera_id] = set()
        self.camera_histories[camera_id].add(local_track_id)
        self.active_cameras.add(camera_id)


class CrossCameraTracker:
    """
    Manages global identities across multiple cameras using Multi-Feature ReID
    (Spatial Color Histograms + Color Moments + Shape).
    """
    def __init__(self, topology: StoreTopology, similarity_threshold: float = 0.45, max_missing_time: float = 300.0):
        self.topology = topology
        self.global_tracks: Dict[str, GlobalTrack] = {}
        # OSNet embeddings are highly dense 512D vectors, so a threshold of 0.45 is highly robust for viewpoint changes.
        self.similarity_threshold = similarity_threshold
        self.max_missing_time = max_missing_time
        self._next_id = 1
        
        # Mapping: (camera_id, local_track_id) -> global_id
        self.local_to_global: Dict[Tuple[str, int], str] = {}
        
        # Initialize OSNet ReID Model
        logger.info("Initializing OSNet ReID Feature Extractor...")
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.extractor = FeatureExtractor(
            model_name='osnet_x1_0',
            device=device,
            verbose=False
        )
        logger.info(f"OSNet ReID initialized on {device}.")

    def extract_embedding(self, frame: np.ndarray, bbox: Tuple[float, float, float, float]) -> Optional[np.ndarray]:
        """Extract deep learning embedding using OSNet."""
        x1, y1, x2, y2 = [int(v) for v in bbox]
        
        # Bounds check
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        if x2 - x1 < 20 or y2 - y1 < 40:
            return None
            
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
            
        # Convert OpenCV BGR to RGB
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        
        # Extract features (returns a tensor, we move to cpu and numpy)
        try:
            features = self.extractor(crop_rgb)
            embedding = features.cpu().numpy().flatten()
            
            # L2 normalize the embedding
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
                
            return embedding
        except Exception as e:
            logger.error(f"ReID extraction failed: {e}")
            return None

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    def remove_local_track(self, camera_id: str, local_track_id: int) -> Optional[str]:
        """Called when a camera tracker loses a person."""
        mapping_key = (camera_id, local_track_id)
        if mapping_key in self.local_to_global:
            global_id = self.local_to_global[mapping_key]
            if global_id in self.global_tracks:
                self.global_tracks[global_id].active_cameras.discard(camera_id)
            return global_id
        return None

    def associate_track(self, camera_id: str, local_track_id: int, frame: np.ndarray, bbox: Tuple[float, float, float, float], timestamp: float) -> str:
        """
        Takes a local track from a specific camera, extracts its embedding,
        and associates it with a global track ID.
        """
        # Cleanup stale tracks
        self._cleanup_stale_tracks(timestamp)

        mapping_key = (camera_id, local_track_id)
        embedding = self.extract_embedding(frame, bbox)

        if embedding is None:
            # Fallback if crop is invalid, use existing mapping or create new
            if mapping_key in self.local_to_global:
                return self.local_to_global[mapping_key]
            
            global_id = f"V_GL_{self._next_id:04d}"
            self._next_id += 1
            self.local_to_global[mapping_key] = global_id
            return global_id

        # 1. If we already mapped this local track, just update it
        if mapping_key in self.local_to_global:
            global_id = self.local_to_global[mapping_key]
            if global_id in self.global_tracks:
                self.global_tracks[global_id].update(embedding, timestamp, camera_id, local_track_id)
            return global_id

        # 2. Try to match with an existing global track (Cross-Camera ReID)
        best_match_id = None
        best_sim = -1.0

        for gid, gtrack in self.global_tracks.items():
            # Camera exclusion rule: 
            # If this global track is already ACTIVE on this camera, it cannot be the same person.
            if camera_id in gtrack.active_cameras:
                continue
                
            recent_cam = gtrack.last_camera
            valid_transition = (
                recent_cam is None
                or recent_cam == camera_id
                or self.topology.is_valid_transition(recent_cam, camera_id)
            )

            # Topology is a hint, not a hard gate. In overlapping CCTV views the
            # same person can appear to jump from entrance/internal to billing.
            threshold = self.similarity_threshold
            time_gap = max(0.0, timestamp - gtrack.last_seen)
            if time_gap <= 3.0:
                threshold -= 0.08
            if self.topology.get_role(camera_id) == CameraRole.BILLING:
                threshold -= 0.05
            
            # Phase 2: Room-Aware Overlap Logic
            # If transitioning between cameras in the exact same room (e.g., CAM_1 to CAM_5),
            # heavily prioritize ID reuse to prevent duplicates from overlapping fields of view.
            if self.topology.is_same_room(recent_cam, camera_id):
                threshold -= 0.10
                if time_gap <= 5.0:
                    threshold -= 0.05 # Massive relaxation for immediate same-room handoffs
            
            if not valid_transition:
                threshold += 0.10
                
            sim = self._cosine_similarity(embedding, gtrack.embedding)
            if sim > threshold and sim > best_sim:
                best_sim = sim
                best_match_id = gid

        if best_match_id:
            # Match found!
            logger.debug("Matched %s (cam %s) to %s (sim: %.2f)", local_track_id, camera_id, best_match_id, best_sim)
            self.global_tracks[best_match_id].update(embedding, timestamp, camera_id, local_track_id)
            self.local_to_global[mapping_key] = best_match_id
            return best_match_id
            
        # 3. No match found, create new global track
        global_id = f"V_GL_{self._next_id:04d}"
        self._next_id += 1
        
        self.global_tracks[global_id] = GlobalTrack(global_id, embedding, timestamp)
        self.global_tracks[global_id].update(embedding, timestamp, camera_id, local_track_id)
        
        self.local_to_global[mapping_key] = global_id
        return global_id

    def _cleanup_stale_tracks(self, current_time: float):
        """Remove global tracks that haven't been seen for a long time."""
        to_delete = []
        for gid, track in self.global_tracks.items():
            if current_time - track.last_seen > self.max_missing_time:
                to_delete.append(gid)
                
        for gid in to_delete:
            del self.global_tracks[gid]
            # Clean up mapping references
            keys_to_del = [k for k, v in self.local_to_global.items() if v == gid]
            for k in keys_to_del:
                del self.local_to_global[k]
