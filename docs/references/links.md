# 낙상 감지 규칙 참고 논문

조건: 일반 RGB 카메라 + 관절 좌표(pose/keypoint), 사람이 읽을 수 있는 규칙(각도·높이·속도·유지 시간) 위주, 2021년 이후 위주, 최근 survey 1편.
확인 방법: 2026-10-28에 아래 링크를 직접 열어 제목·저자·연도·공개 여부를 확인함. 페이지에서 확인하지 못한 세부 내용은 "미확인"으로 표시.

| 제목 | 연도 | 링크 | 무료로 받을 수 있는지 | 이 논문에서 쓸 규칙 한 줄 요약 |
|---|---|---|---|---|
| Pose-Based Fall Detection System: Efficient Monitoring on Standard CPUs (Mali, Jaiswal) | 2025 | https://arxiv.org/abs/2503.19501v1 | 예 (arXiv PDF·HTML) | MediaPipe 관절로 몸통-다리 각도(어깨-엉덩이 vs 엉덩이-무릎)가 60°~120°이면 낙상 자세 후보. 처음 키 대비 높이 비율, 머리-바닥 거리, 움직임 속도를 가중 점수로 합치고 20프레임 버퍼에서 투표해 오탐을 줄임 (높이 비율·속도의 정확한 기준값은 미확인) |
| ElderFallGuard: Real-Time IoT and Computer Vision-Based Fall Detection System for Elderly Safety (Riahi, Bappy, Islam) | 2025 | https://arxiv.org/abs/2505.11845v1 | 예 (arXiv, CC BY 4.0) | MediaPipe 자세에서 엎드린 자세가 3초 넘게 유지되고, 동시에 움직임이 크게 줄어든 상태가 2초 넘게 이어질 때 낙상으로 판정 (자세 종류 분류에는 랜덤 포레스트 사용, 낙상 판정 자체는 시간 규칙) |
| Omobot: a low-cost mobile robot for autonomous search and fall detection (Ahamad, Ataei, Devabhaktuni, Dhiman) | 2024 | https://arxiv.org/abs/2408.05315 | 예 (arXiv, CC BY 4.0) | YOLOv8-Pose 관절로, 어깨-엉덩이 길이 l 기준 "어깨 y > 발 y − l, 엉덩이 y > 발 y − l/2, 어깨 y > 엉덩이 y − l/2"를 모두 만족하거나 사람 상자가 세로보다 가로가 길면 낙상 (로봇 카메라 시점을 사람 키 높이로 변환해 사용, 카메라가 RGB인지는 페이지에서 미확인) |
| Human Fall Down Recognition Using Coordinates Key Points Skeleton (Ali, Hussain, Sadiq), iJOE 18(2) | 2022 | https://researchonline.ljmu.ac.uk/id/eprint/18210/ | 예 (기관 저장소 PDF, CC BY) | OpenPose 관절로 머리·어깨 중심 좌표, 머리 중심과 바닥 사이 거리, 어깨 중심선과 바닥의 각도를 낙상 판단에 사용 (고정 기준값인지 분류기인지, 구체적 수치는 미확인) |
| Fall Detection Based on Key Points of Human-Skeleton Using OpenPose (Chen, Jiang, Guo, Ni), Symmetry 12(5):744 | 2020 | https://doi.org/10.3390/sym12050744 | 예 (CC BY 4.0. MDPI 페이지는 자동 접속 거부(403)라 사용자가 받아 둔 `symmetry-12-00744.pdf`로 본문 확인, 정리는 `docs/rules_from_papers.md`) | 2021년 이전이지만 많이 인용되는 규칙 기반 기준 논문: 엉덩이 중심의 하강 속도, 몸 중심선과 바닥의 각도, 사람 상자의 가로세로 비율 세 가지로 판정하고, 넘어진 뒤 다시 일어나는 경우도 고려 (기준값은 미확인) |
| Deep Learning for Computer Vision based Activity Recognition and Fall Detection of the Elderly: a Systematic Review (Gaya-Morey, Manresa-Yee, Buades-Rubio) — survey | 2024 | https://arxiv.org/abs/2401.11790 | 예 (arXiv, CC BY 4.0) | 최근 survey: 영상 기반 낙상 감지에 쓰인 데이터셋, 모델, 장비(깊이·열화상 포함)와 장단점을 정리. 딥러닝 위주라 규칙보다는 데이터셋 선택과 평가 방법 참고용 (관절 기반 방법을 얼마나 다루는지는 미확인) |

## 제외한 후보
- Unsupervised Keypoints for Real-Time Fall Detection (arXiv 2607.15400, 2026): 순환 신경망(variational recurrent model) 중심이라 조건(딥러닝 중심 제외)에 맞지 않음.
- PMC12475850: 페이지가 로봇 확인(reCAPTCHA)으로 열리지 않아 내용 미확인, 표에 넣지 않음.
