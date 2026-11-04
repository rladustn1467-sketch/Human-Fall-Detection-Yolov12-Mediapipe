# Tailscale 원격 접속

- **기록일:** 2026-11-04
- **용도:** 집 밖이나 다른 망의 기기에서 학교 PC의 서버를 시험하고 시연하기. 공개 HTTPS 대신 씁니다.

계정 주소와 Tailscale IP는 저장소에 적지 않습니다. 관리 화면이나 `tailscale status` 로 확인합니다.

## 현재 구성

| 항목 | 내용 |
|---|---|
| 버전 | 1.104.5 |
| 기기 | 운영 PC, 아이폰 |
| **로그인 만료일** | **운영 PC, 아이폰 모두 2027-05-03** |
| 운영 PC 설정 | DNS 받기 꺼짐, 경로 받기 꺼짐, Exit Node 없음, 서브넷 라우팅 없음 |
| Funnel, Serve | 사용 안 함 |
| 서버 주소 | `http://<운영 PC Tailscale 주소>:8000/app/next/` |

만료일 전에 다시 로그인해야 합니다. 시연 일정이 만료일 근처라면 관리 화면의 Machines 에서 운영 PC의 키 만료를 꺼 둡니다.

## 시험 결과 (2026-11-04)

아이폰을 LTE로 두고 Safari 에서 확인했습니다. 앱이 아니라 브라우저 시험입니다.

- 건강 확인, 로그인, 가족·집·기기·낙상·알림 조회, 연결을 끊었다가 복구 모두 성공
- 도쿄 중계로 시작해 직접 연결로 전환됨
- 방화벽의 기존 규칙 변경 0개. Tailscale 이 자동으로 3개 추가 (`Tailscale-Process`, `Tailscale-In` 2개)

## 접근 범위

`Tailscale-In` 규칙은 Tailscale 주소로 들어오는 **모든 포트**를 허용합니다. 이 규칙은 Tailscale 이 직접 관리하므로 고치지 않습니다. 대신 **Tailscale 접근 정책**으로 8000번만 통과시킵니다. 정책에서 막힌 패킷은 방화벽까지 오지 않습니다.

Access Controls 에 넣을 내용입니다. `<운영 PC 주소>` 는 `tailscale ip -4` 로 나오는 값입니다.

```json
{
  "hosts": {
    "fall-server": "<운영 PC 주소>",
  },
  "acls": [
    {
      "action": "accept",
      "src": ["autogroup:member"],
      "proto": "tcp",
      "dst": ["fall-server:8000"],
    },
  ],
  "ssh": [],
}
```

저장 뒤 확인할 것:

1. 아이폰 Safari 에서 `http://<운영 PC 주소>:8000/api/v2/health` 가 열림
2. 아이폰 Safari 에서 `http://<운영 PC 주소>:3336/` 이 열리지 않음
3. 운영 PC 에서 `tailscale debug netmap` 의 `PacketFilter` 대상이 8000번 하나뿐임

되돌리기: 관리 화면 Access Controls 의 변경 기록에서 이전 정책으로 복구합니다.

정책을 적용하면 운영 PC 쪽에서 먼저 아이폰으로 보내는 `tailscale ping` 같은 통신은 막힐 수 있습니다. 서버 접속에는 영향이 없습니다.

## 주의

- 다른 사람을 초대하지 않습니다.
- Funnel 을 켜지 않습니다. 켜면 인터넷에 공개됩니다.
- `tailscale serve` 를 쓰지 않습니다. 요청이 PC 내부에서 온 것처럼 보여, 이 PC에서만 열리도록 막아 둔 신고 기록 페이지가 열릴 수 있습니다.
- 학교 PC 에서 쓰는 것이므로 학교 규정을 확인합니다.
- 서버가 꺼지면 Tailscale 이 연결돼 있어도 접속되지 않습니다.
