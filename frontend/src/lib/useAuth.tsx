"use client";

/**
 * 로그인 상태 (DAY 15).
 *
 * ## 토큰을 들고 있지 않는다
 *
 * 세션은 `httponly` 쿠키에 있고 자바스크립트는 그것을 읽지 못한다.
 * 여기서 들고 있는 것은 **누구인지**뿐이다. 토큰을 localStorage 에
 * 두면 XSS 한 번에 세션이 통째로 털린다.
 *
 * ## 401 을 한 곳에서 처리한다
 *
 * 세션은 만료된다. 화면마다 401 을 따로 처리하면 어떤 화면은 빼먹고,
 * 그 화면만 "로그인했는데 빈 화면"이 된다. `api.ts` 가 401 을 만나면
 * 여기로 알려주고, 여기서 한 번에 로그인 화면으로 보낸다.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ApiError, api, onUnauthorized } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  /** saas 배포라 로그인이 반드시 필요한가. local 이면 false. */
  required: boolean;
  /** 이 서버에 계정이 하나도 없는가. 첫 가입자에게 알려준다. */
  firstUser: boolean;
  loading: boolean;
  /** 로그인·가입 폼에 보여줄 오류. 사용자가 고칠 수 있는 것. */
  error: string | null;
  /**
   * 백엔드에 닿지 못했을 때만 채운다.
   *
   * 폼 오류와 **반드시 분리한다.** 하나로 합쳐 뒀다가, 비밀번호가 짧다는
   * 검증 실패가 "백엔드에 닿지 못했습니다"로 표시되고 로그인 폼이 통째로
   * 사라지는 것을 브라우저에서 직접 보고 고쳤다. 사용자는 자기 비밀번호가
   * 아니라 서버를 의심하게 된다.
   */
  connectionError: string | null;
  signUp: (email: string, password: string, name?: string) => Promise<void>;
  logIn: (email: string, password: string) => Promise<void>;
  logOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [required, setRequired] = useState(false);
  const [firstUser, setFirstUser] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setUser(me.user);
      setRequired(me.required);
      setFirstUser(me.first_user);
      setConnectionError(null);
    } catch (e) {
      // `/api/auth/me` 는 로그인 전에도 200 이어야 한다. 여기서 실패하면
      // 백엔드에 닿지 못한 것이다 — 로그인 화면이 아니라 그 사실을 말한다.
      setConnectionError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 마운트 시 한 번 서버에 물어본다. setState 는 `await` **뒤**에서
    // 일어나지만 린터는 async 경계를 넘어 보지 못해 오탐을 낸다 —
    // 같은 설명이 `useLoader.ts` 에 자세히 적혀 있다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  // 세션이 만료되면 어느 화면에서든 여기로 온다.
  useEffect(() => onUnauthorized(() => setUser(null)), []);

  const run = useCallback(
    async (fn: () => Promise<{ user: User }>) => {
      setError(null);
      try {
        const out = await fn();
        setUser(out.user);
        await refresh();
      } catch (e) {
        const msg =
          e instanceof ApiError
            ? e.message
            : e instanceof Error
              ? e.message
              : String(e);
        setError(msg);
        throw e;
      }
    },
    [refresh],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      required,
      firstUser,
      loading,
      error,
      connectionError,
      signUp: (email, password, name) =>
        run(() => api.signUp(email, password, name)),
      logIn: (email, password) => run(() => api.logIn(email, password)),
      logOut: async () => {
        await api.logOut();
        setUser(null);
        await refresh();
      },
      refresh,
    }),
    [user, required, firstUser, loading, error, connectionError, run, refresh],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("AuthProvider 안에서만 쓸 수 있습니다");
  return ctx;
}
