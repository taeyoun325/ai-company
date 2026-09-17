import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // 이 폴더를 루트로 못박는다. 안 박으면 Next 가 상위로 거슬러 올라가
  // 홈 디렉터리의 package-lock.json 을 집어 경고를 낸다.
  turbopack: { root: path.resolve(__dirname) },

  async rewrites() {
    // 개발 중에는 프론트(3000)에서 /api 를 백엔드(8000)로 그대로 넘긴다.
    // SSE 도 이 경로를 탄다 — CORS 설정을 따로 두지 않기 위해서다.
    const backend = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
