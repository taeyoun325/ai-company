"use client";

/**
 * URL 경로에서 프로젝트 slug 를 꺼낸다.
 *
 * ## 왜 감싸는가
 *
 * 프로젝트 slug 에는 한글이 들어간다("20260921-사칙연산-계산기"). Next 의
 * 동적 세그먼트는 그것을 **퍼센트 인코딩된 채로** 넘겨주는데, 그대로
 * `encodeURIComponent` 에 넣으면 두 번 인코딩되어 백엔드가 다른 문자열로
 * 읽는다. 증상은 "404 가 아니라 **빈 화면**" 이라서 원인을 찾기 어렵다.
 * 실제로 작업 로그가 통째로 비는 것으로 한 번 겪었다.
 *
 * 한 번만 푼다. 두 번 풀면 이름에 `%` 가 들어간 프로젝트가 깨진다.
 */
export function useSlug(params: { slug: string }): string {
  try {
    return decodeURIComponent(params.slug);
  } catch {
    // 인코딩이 깨진 URL. 원문 그대로 넘겨 백엔드가 404 로 답하게 둔다 —
    // 여기서 삼키면 "왜 빈 화면인지" 알 수 없게 된다.
    return params.slug;
  }
}
