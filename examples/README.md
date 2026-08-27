# 사용 예시

동봉된 합성 로그 2종으로 두 경로를 모두 볼 수 있습니다.

```bash
# 장애 로그 -> critical 분기 -> 근본 원인 보고서
log-triage data/incident.log --backend claude-cli

# 평시 로그 -> digest 분기 -> 참고 포인트 보고서
log-triage data/normal.log --backend claude-cli
```
