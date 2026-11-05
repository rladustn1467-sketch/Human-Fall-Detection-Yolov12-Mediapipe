# Fall Detection Algorithm Documentation

## Overview

This document outlines the fall detection algorithm implemented in our system, which uses a combination of computer vision techniques, human pose estimation, and biomechanical analysis to detect falls in real-time video feeds. The algorithm is designed to identify and classify four types of falls: step and fall, slip and fall, trip and fall, and stump and fall.

## System Architecture

The fall detection system follows a pipeline architecture:

1. **Person Detection**: Using YOLOv12 to identify and localize people in the frame
2. **Pose Estimation**: Using MediaPipe to extract skeletal keypoints of detected persons
3. **Feature Extraction**: Calculating biomechanical features from the skeletal pose
4. **Fall Detection**: Analyzing features to detect falls based on multi-criteria evaluation
5. **Fall Classification**: Categorizing detected falls into specific fall types

## Key Components

### 1. Person Detection (YOLOv12)

The system uses YOLOv12, a state-of-the-art object detection model, to locate people in each video frame.

```
Function DetectPersons(frame):
    # Convert frame to appropriate format if needed
    processed_frame = PreprocessFrame(frame)
    
    # Run YOLOv12 inference
    results = YOLOv12.Detect(processed_frame, confidence_threshold=0.5)
    
    # Filter for person class (class_id=0 in COCO dataset)
    person_boxes = []
    For each detection in results:
        If detection.class_id == 0 AND detection.confidence > confidence_threshold:
            person_boxes.append(detection.bounding_box)
    
    Return person_boxes
```

### 2. Pose Estimation (MediaPipe)

For each detected person, we extract skeletal keypoints using MediaPipe Pose.

```
Function AnalyzePose(frame, person_box):
    # Extract person ROI
    x1, y1, x2, y2 = person_box
    person_img = frame[y1:y2, x1:x2]
    
    # Skip if ROI is empty
    If person_img is empty:
        Return None, None
    
    # Convert to RGB for MediaPipe
    rgb_img = ConvertToRGB(person_img)
    
    # Process with MediaPipe
    pose_results = MediaPipe.Process(rgb_img)
    
    If no pose landmarks detected:
        Return None, None
    
    # Extract landmarks
    landmarks = []
    For each landmark in pose_results.pose_landmarks:
        landmarks.append((landmark.x, landmark.y, landmark.z, landmark.visibility))
    
    # Calculate pose features
    pose_features = CalculatePoseFeatures(landmarks)
    
    Return landmarks, pose_features
```

### 3. Feature Extraction

The system calculates a comprehensive set of biomechanical features from the pose landmarks:

```
Function CalculatePoseFeatures(landmarks):
    # Extract key points (head, shoulders, hips, knees, ankles)
    key_points = [0, 11, 12, 23, 24, 25, 26, 27, 28]
    key_landmarks = ExtractPositions(landmarks, key_points)
    
    # Calculate height (vertical distance between head and feet)
    head_y = landmarks[0].y
    ankle_y = (landmarks[27].y + landmarks[28].y) / 2
    height = abs(ankle_y - head_y)
    
    # Calculate spine orientation (angle with vertical)
    mid_shoulder = CalculateMidpoint(landmarks[11], landmarks[12])
    mid_hip = CalculateMidpoint(landmarks[23], landmarks[24])
    spine_angle = CalculateAngle(mid_shoulder, mid_hip, vertical_axis)
    
    # Calculate bounding box and aspect ratio
    bbox = CalculateBoundingBox(landmarks)
    aspect_ratio = bbox.height / bbox.width
    
    # Calculate distances between key points
    shoulder_to_hip_distance = CalculateDistance(mid_shoulder, mid_hip)
    hip_to_feet_distance = CalculateDistance(mid_hip, CalculateMidpoint(landmarks[27], landmarks[28]))
    
    # Calculate motion metrics (if previous frames exist)
    velocity_y, velocity_x, acceleration, jerk = CalculateMotionMetrics(mid_shoulder, history)
    
    # Create feature dictionary
    features = {
        "height": height,
        "angle": spine_angle,
        "velocity_y": velocity_y,
        "velocity_x": velocity_x,
        "acceleration": acceleration,
        "jerk": jerk,
        "aspect_ratio": aspect_ratio,
        "shoulder_to_hip_distance": shoulder_to_hip_distance,
        "hip_to_feet_distance": hip_to_feet_distance,
        "timestamp": current_time
    }
    
    # Update pose history
    history.append(features)
    If history.length > MAX_HISTORY_SIZE:
        history.removeOldest()
    
    Return features
```

### 4. Fall Detection Algorithm

The core fall detection algorithm uses a multi-criteria approach to identify falls:

```
Function DetectFall(pose_features, history):
    If pose_features is empty:
        Return False
    
    # Initialize criteria counter
    fall_criteria_met = 0
    
    # Criterion 1: Non-upright angle (person tilted)
    If abs(pose_features.angle) > ANGLE_THRESHOLD:
        fall_criteria_met += 1
    
    # Criterion 2: Aspect ratio indicates horizontal position
    If pose_features.aspect_ratio < 1.5:  # More horizontal than vertical
        fall_criteria_met += 1
    
    # Only check motion-based criteria if we have enough history
    If history.length > 5:
        current = pose_features
        previous = history[-6]  # 5 frames ago
        
        # Criterion 3: Significant vertical movement (falling down)
        If current.mid_shoulder_y - previous.mid_shoulder_y > FALL_THRESHOLD:
            fall_criteria_met += 1
        
        # Criterion 4: Rapid change in angle
        If abs(current.angle - previous.angle) > 30:
            fall_criteria_met += 1
        
        # Criterion 5: Acceleration spike (typical in falls)
        If abs(current.acceleration) > 0.2:
            fall_criteria_met += 1
    
    # Fall is detected if multiple criteria are met (reduces false positives)
    is_fall = fall_criteria_met >= 3
    
    If is_fall:
        # Classify fall type
        fall_type = ClassifyFallType(pose_features, history)
        Return True, fall_type
    Else:
        Return False, None
```

### 5. Fall Classification

The algorithm classifies falls into four distinct categories:

```
Function ClassifyFallType(pose_features, history):
    If history.length < 5:
        Return "unknown"
    
    current = pose_features
    previous = history[-5]
    
    # Extract key metrics
    angle_change = abs(current.angle - previous.angle)
    velocity_y = current.velocity_y
    velocity_x = current.velocity_x
    acceleration = current.acceleration
    jerk = current.jerk
    
    # Step and Fall: Gradual angle change, moderate velocity, person loses footing
    If angle_change > 20 AND angle_change < 50 AND 
       velocity_y > 0.1 AND velocity_y < 0.4 AND
       abs(velocity_x) < 0.15 AND
       current.aspect_ratio < 1.5:
        Return "step_and_fall"
    
    # Slip and Fall: Rapid angle change, high velocity, often backward motion
    Else If angle_change > 45 AND
            velocity_y > 0.3 AND
            acceleration > 0.2 AND
            abs(jerk) > 0.1 AND
            current.aspect_ratio < 1.5:
        Return "slip_and_fall"
    
    # Trip and Fall: Forward momentum, moderate angle change, person pitches forward
    Else If angle_change > 30 AND
            abs(velocity_x) > 0.1 AND
            velocity_y > 0.2 AND
            current.aspect_ratio < 1.5:
        Return "trip_and_fall"
    
    # Stump and Fall: Minimal horizontal movement, vertical drop, from standing still
    Else If abs(velocity_x) < 0.08 AND
            velocity_y > 0.2 AND
            angle_change > 25 AND
            current.aspect_ratio < 1.5:
        Return "stump_and_fall"
    
    # Fall type can't be determined
    Return "unknown"
```

## Fall Type Definitions

### 1. Step and Fall
- **Definition**: A fall that occurs when a person misplaces their foot while walking or stepping, losing their balance
- **Key Characteristics**:
  - Gradual angle change (20°-50°)
  - Moderate vertical velocity (0.1-0.4)
  - Limited horizontal velocity
  - Person ends in horizontal position

### 2. Slip and Fall
- **Definition**: A fall that occurs when a person loses traction with the ground surface
- **Key Characteristics**:
  - Rapid angle change (>45°)
  - High vertical velocity (>0.3)
  - High acceleration (>0.2)
  - Significant jerk (rate of change of acceleration)
  - Often has backward motion component

### 3. Trip and Fall
- **Definition**: A fall that occurs when a person's foot or leg is impeded by an object
- **Key Characteristics**:
  - Moderate angle change (>30°)
  - Significant horizontal velocity (>0.1)
  - Moderate vertical velocity (>0.2)
  - Person typically pitches forward

### 4. Stump and Fall
- **Definition**: A fall that occurs when a person collapses or drops vertically
- **Key Characteristics**:
  - Minimal horizontal movement (<0.08)
  - Significant vertical velocity (>0.2)
  - Moderate angle change (>25°)
  - Person typically drops straight down

## Performance Considerations

The algorithm's performance is influenced by several factors:

1. **Frame Rate**: Higher frame rates improve motion tracking accuracy
2. **Resolution**: Higher resolutions improve pose estimation accuracy
3. **Lighting**: Good lighting conditions significantly improve detection reliability
4. **Occlusion**: Partial occlusion may reduce accuracy

## Thresholds and Parameters

The algorithm relies on carefully tuned thresholds:

- `ANGLE_THRESHOLD`: 45° (angle with vertical axis)
- `FALL_THRESHOLD`: 0.4 (vertical movement threshold)
- `MIN_CRITERIA`: 3 (minimum criteria needed for fall detection)
- `HISTORY_SIZE`: 15 (frames of pose history to maintain)

These parameters can be adjusted based on specific deployment requirements and environments.

## Limitations

1. **Occlusion**: Falls that occur behind furniture or other obstacles may not be detected
2. **Distance**: Detection accuracy decreases for persons very far from the camera
3. **Multiple Falls**: Simultaneous falls by multiple people may not all be classified correctly
4. **Unusual Falls**: Falls with very unusual patterns may be misclassified or missed

The system continues to improve through ongoing refinement of the algorithms and thresholds. 