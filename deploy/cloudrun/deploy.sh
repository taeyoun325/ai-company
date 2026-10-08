#!/bin/sh
# AI COMPANY — Cloud Run + Firebase Hosting 배포 (DAY 27).
#
#   sh deploy/cloudrun/deploy.sh setup     # 처음 한 번: API·버킷·저장소·서비스 계정·비밀
#   sh deploy/cloudrun/deploy.sh build     # 이미지 (Cloud Build — 로컬 docker 불필요)
#   sh deploy/cloudrun/deploy.sh deploy    # Cloud Run 서비스 + Firebase Hosting (설정 전부 다시 쓴다)
#   sh deploy/cloudrun/deploy.sh release   # 새 이미지만 + Hosting 캐시 비우기 (설정은 그대로)
#
# 저장소 루트에서 실행한다. gcloud 로그인과 firebase 로그인이 필요하다.
set -eu

PROJECT=${PROJECT:-ai-company-1c4da}
REGION=${REGION:-asia-northeast3}
SERVICE=${SERVICE:-ai-company}
BUCKET=${BUCKET:-$PROJECT-state}
SA=ai-company-run@$PROJECT.iam.gserviceaccount.com
IMAGE=$REGION-docker.pkg.dev/$PROJECT/ai-company/app:latest

# Git Bash 는 '/mnt/state' 같은 인자를 윈도우 경로로 바꿔 버린다.
export MSYS2_ARG_CONV_EXCL="volume=;--args=;httpGet"

case "${1:-}" in
setup)
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
    artifactregistry.googleapis.com storage.googleapis.com iam.googleapis.com \
    secretmanager.googleapis.com --project "$PROJECT"
  gcloud artifacts repositories create ai-company --repository-format=docker \
    --location "$REGION" --project "$PROJECT" || true
  gcloud storage buckets create "gs://$BUCKET" --location "$REGION" \
    --uniform-bucket-level-access --public-access-prevention --project "$PROJECT" || true
  # 버전 관리: 잘못 덮어쓴 JSON·산출물을 되돌릴 수 있게.
  gcloud storage buckets update "gs://$BUCKET" --versioning
  # 서비스 계정은 **이 버킷 하나**만 만질 수 있다. 프로젝트 권한은 없다.
  gcloud iam service-accounts create ai-company-run --project "$PROJECT" \
    --display-name "AI COMPANY Cloud Run (state bucket only)" || true
  gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
    --member "serviceAccount:$SA" --role roles/storage.objectAdmin
  if ! gcloud secrets describe byok-secret --project "$PROJECT" >/dev/null 2>&1; then
    head -c 32 /dev/urandom | base64 | tr -d '\n' | \
      gcloud secrets create byok-secret --data-file=- --project "$PROJECT"
  fi
  gcloud secrets add-iam-policy-binding byok-secret --project "$PROJECT" \
    --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor
  ;;
build)
  gcloud builds submit --config deploy/cloudrun/cloudbuild.yaml \
    --project "$PROJECT" --region "$REGION" .
  ;;
deploy)
  # max-instances 1 은 **보장이 아니다**(리비전마다 따로 센다). 쓰는 쪽을 하나로
  # 묶는 건 supervisor.py 의 임대다. 이 값은 평소 비용을 묶는 용도다.
  #
  # 시작 검사는 **TCP** 다. 감독자의 앞문(supervisor.py · Front)은 임대를 곧
  # 받을 수 있어 보이면 바로 열리고, 그때부터 온 요청은 앱이 준비될 때까지
  # 실패하지 않고 붙잡힌다. 그래서 Cloud Run 이 새 리비전으로 일찍 넘겨도 된다 —
  # 늦게 넘기면(HTTP 검사) 그 사이 옛 인스턴스는 이미 넘겨준 뒤라 요청이
  # 실패했다(실측). 생존 검사는 백엔드까지 닿는 HTTP 다.
  #
  # --timeout 900: SSE 는 서버가 10분(SSE_MAX_SECONDS)마다 닫고 브라우저가
  # 이어 붙는다. 1시간이던 때 Hosting 뒤의 버려진 연결이 1시간씩 붙어 있었다.
  gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" \
    --image "$IMAGE" \
    --execution-environment gen2 \
    --service-account "$SA" \
    --min-instances 0 --max-instances 1 \
    --no-cpu-throttling --cpu 2 --memory 2Gi \
    --timeout 900 --concurrency 80 \
    --allow-unauthenticated \
    --add-volume "name=state,type=cloud-storage,bucket=$BUCKET" \
    --add-volume-mount "volume=state,mount-path=/mnt/state" \
    --startup-probe "tcpSocket.port=8080,periodSeconds=1,failureThreshold=240,timeoutSeconds=1" \
    --liveness-probe "httpGet.path=/api/deploy,httpGet.port=8080,periodSeconds=30,failureThreshold=3,timeoutSeconds=5" \
    --set-env-vars "^;^STATE_BUCKET=$BUCKET;PROVIDER_MODE=${PROVIDER_MODE:-mock};PUBLIC_URL=https://$PROJECT.web.app;SANDBOXED=1;OPERATOR_EMAILS=${OPERATOR_EMAILS:-}" \
    --set-secrets "BYOK_SECRET=byok-secret:latest"
  firebase deploy --only hosting --project "$PROJECT"
  ;;
release)
  # 코드만 바뀐 평소 배포. `deploy` 는 환경변수를 --set-env-vars 로 **통째로 다시 쓴다** —
  # 운영 중에 넣은 값(OPERATOR_EMAILS · PROVIDER_MODE · 키 연결)이 기본값으로 돌아간다.
  # 여기서는 이미지만 바꾸고 나머지 설정은 건드리지 않는다.
  gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --image "$IMAGE" --quiet
  # Hosting 은 정적 페이지 HTML 을 1년(s-maxage) 붙들고 있다. 새 이미지는 CSS · JS 조각
  # 이름이 바뀌므로, 옛 HTML 이 남으면 **없는 파일을 불러 화면이 통째로 깨진다**
  # (2026-10-08 실제로 깨졌다 — 이미지만 바꾸고 이 줄을 빼먹었다). 릴리스가 캐시를 비운다.
  firebase deploy --only hosting --project "$PROJECT"
  ;;
*)
  sed -n '2,10p' "$0"
  exit 2
  ;;
esac
