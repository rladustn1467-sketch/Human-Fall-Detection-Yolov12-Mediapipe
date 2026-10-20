# 지킴이 · 낙상 감지 서비스 (웹앱)

가족이 함께 쓰는 낙상 감지·알림 서비스의 모바일 웹앱 화면입니다.
카메라 감지 · 서버 · 119 연동은 이후 연결할 예정이며, 현재는 임시 데이터와 상태 값으로 모든 화면이 동작합니다.

## 현재 구현된 기능

- **온보딩** O-01~O-09: 가입 → 그룹 만들기/참여(QR·초대 코드, 24시간 만료, 매번 새 코드) → 감지 대상 질문 → 개인정보 → 주소(그룹 집 선택/검색) → 현관 비밀번호 → 기기 연결
- **탭 4개**: 홈 / 예방 / 가족 / 설정
  - 홈: 진행 중 사고 배너(마감 빠른 순), 집 단위 감지 현황(정상·주의·감지 중단, 이상 시 자동 펼침·문제 기기 맨 위), 내 폰 카메라 카드 / "알림만 받는 중" 카드, 설정 미완료 배너, 최근 알림
  - 가족: 집별 구성원 + "알림만 받는 분", 초대하기, 집 관리, 그룹 나가기
  - 설정: 내 프로필, 알림 설정, 회원 탈퇴
- **하위 화면** S-01~S-12 (기기 상세 시트, 낙상 이력 목록/상세, 구성원 상세, 집 상세, 초대, 비밀번호 변경, 그룹 나가기·회원 탈퇴 확인, 프로필 수정, 알림 설정, 감지 켜기 흐름)
- **긴급 이벤트** E-01~E-07: 어떤 화면 위에서도 전체 화면으로 표시. 낙상자 / 가족 / 대상자 선택 / 119 신고 확인 / 확인 중 / 신고 완료·종료
- **권한 규칙**: 개인정보는 본인만 수정, 주소·비밀번호·기기는 그 집에 연결된 사람만 수정, 비밀번호 값은 어디에도 표시하지 않고 "등록됨/미등록"만 표시
- **타이머**: 기준 시각(감지 시각, 자동 신고 예정 시각)을 상태로 저장하고 `예정 시각 − 현재 시각`으로 계산. 모든 화면이 같은 마감 시각 공유. 도움 요청을 반복해도 180초 마감은 처음 요청 기준 유지

## 진입 경로 (URL)

| 경로 | 설명 |
|---|---|
| `index.html#/` | 홈 |
| `#/prevent` · `#/family` · `#/settings` | 탭 화면 |
| `#/history` · `#/history/:id` | 낙상 이력 목록 · 상세 |
| `#/family/member/:id` · `#/family/home/:id` · `#/family/invite` | 구성원 · 집 상세 · 초대 |
| `#/settings/profile` · `#/settings/notifications` | 프로필 수정 · 알림 설정 |
| `#/ob/signup` `#/ob/group` `#/ob/invite` `#/ob/join` `#/ob/ask` `#/ob/info` `#/ob/address` `#/ob/password` `#/ob/device` | 온보딩 |
| `#/enable/info` … `#/enable/device` | 감지 켜기(S-12, 온보딩 O-06~O-09 재사용) |
| `#/join?code=XXXXXX` | 초대 링크 |
| `index.html?as=u1…u4` | 사용자를 고정해서 열기(개발 확인용 동시 보기에서 사용) |
| **`dev.html`** | **개발 확인용 경로** — 일반 화면 어디에도 링크 없음. 낙상 발생, 사용자 전환(김민준/이서연/박순자/김민호), 타이머 배속(×1/5/10/30)·시간 건너뛰기, 사용자별 동시 보기 |

## 파일 구조 (데이터와 UI 분리)

```
index.html          앱 셸
dev.html            개발 확인용 콘솔 (별도 URL)
css/main.css        디자인 시스템
js/api.js           ★ 데이터 공급 계층 — 임시 데이터. 실제 API로 교체하는 지점
js/store.js         ★ 상태 · 선택자(Sel) · 동작(Act) · 사고 상태 전이(advance = 서버 대행 자리)
js/ui.js            공통 UI(시트·확인창·토스트·포맷터·가공 이미지·QR)
js/router.js        해시 라우터 · 탭바
js/onboarding.js    O-01~O-09, S-12
js/home.js          홈, 기기 상세, 이력 목록/상세
js/family.js        가족, 구성원, 집, 초대, 주소·비밀번호·기기 추가 시트
js/settings.js      설정, 프로필, 알림 설정, 탈퇴
js/prevent.js       ★ 예방 탭 독립 모듈 (통째로 교체 가능)
js/emergency.js     긴급 이벤트 E-01~E-07 오버레이
js/app.js           시작 · 화면 보호(guard) · 구독
```

### 예방 탭 교체 방법
`js/prevent.js` 파일만 교체하면 됩니다. 계약은 `window.FD_PREVENT.render(container)` (선택: `destroy()`) 하나뿐이며, 다른 코드와 의존성이 없습니다. 현재는 탭 제목만 있는 최소 화면입니다.

### 실제 서버 연결 시
- `js/api.js` 의 `loadSnapshot / readSnapshot / writeSnapshot / searchAddress` 를 서버 호출로 교체
- 사고 이벤트(`incident` 객체: `detected → no_response/help → checking → reported/closed`)는 서버 데이터로 주입. `store.js` 의 `advance()`(60초 무응답 전이, 자동 119 신고)는 서버가 맡도록 제거

## 데이터 모델 (`FD.Store.state`)

- `groups` / `people`(이름·휴대전화·감지 대상자 여부·생년월일·지병·복용약·homeIds·phoneCamera·prefs) / `homes`(주소·centralPw·doorPw: 불리언만 보관) / `devices`(type·location·status: ok|disconnected|off)
- `incidents`: `detectedAt`, `status`, `familyNotifiedAt`, `autoReportAt`, `helpTimes[]`, `checkedBy/At`, `reportedBy/At`, `closedAt`, `log[]`
- `history`: 과거 낙상 이력, `notifs`: 가족 알림 기록, `clock`: 배속 가능한 가상 시계
- 저장소: 브라우저 `localStorage` (같은 브라우저의 여러 탭이 같은 사고 상태를 공유)

## 아직 구현되지 않은 것

- 실제 카메라 연결·낙상 감지, 서버, 119 접수·푸시 알림, 실제 가입 인증
- 예방 탭 콘텐츠(다른 팀 담당)
- 기기 연결 세부 흐름(추후 확정), 알림 설정 세부 항목(추후 확정)
- 확인 후 5·10·15분 되묻기는 화면 표시만 구현(푸시 발송은 서버 담당)

## 다음 단계 제안

1. `api.js` 를 실제 REST/WebSocket 으로 교체, `advance()` 를 서버 이벤트로 대체
2. 푸시 알림(웹 푸시/앱)과 긴급 화면의 소리·진동 연결
3. 예방 탭 모듈 연결
4. 주소 검색(도로명주소 API)과 지도 연동

> 참고: 정적 사이트이므로 이 웹앱의 로그인·권한 체크는 화면 구성용입니다. 실제 서비스에서는 서버 인증이 필요합니다.
