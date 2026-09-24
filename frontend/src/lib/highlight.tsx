/**
 * 아주 가벼운 문법 강조 (패키지 없이).
 *
 * 정확한 파서가 아니라 정규식 토크나이저다. 산출물 파일 몇 개를 읽기
 * 좋게 색칠하는 게 목적이지, 편집기를 대체하는 게 아니다 — 그래서
 * 언어별 규칙을 완전하게 다루지 않는다(예: 이스케이프가 복잡한 문자열).
 * 틀린 색칠은 있어도, 틀린 텍스트는 절대 없다 — 매칭 안 된 부분은
 * 원문 그대로 통과시킨다.
 */
type TokenKind =
  | "plain" | "comment" | "string" | "number" | "keyword"
  | "func" | "heading" | "bold" | "code" | "punct";

interface Token {
  kind: TokenKind;
  text: string;
}

interface Rule {
  kind: TokenKind;
  re: RegExp;
}

const PY_KEYWORDS =
  "def|return|if|elif|else|for|while|class|import|from|as|with|try|except|" +
  "finally|raise|pass|break|continue|in|is|not|and|or|None|True|False|" +
  "lambda|yield|global|nonlocal|assert|async|await|del|self|match|case";

const JS_KEYWORDS =
  "const|let|var|function|return|if|else|for|while|class|extends|new|" +
  "import|export|from|as|default|try|catch|finally|throw|typeof|instanceof|" +
  "in|of|async|await|yield|null|undefined|true|false|this|super|static|" +
  "interface|type|enum|implements|public|private|protected|readonly";

const RULES: Record<string, Rule[]> = {
  python: [
    { kind: "comment", re: /#.*/y },
    { kind: "string", re: /("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')/y },
    { kind: "func", re: /(?<=def\s)[A-Za-z_]\w*/y },
    { kind: "keyword", re: new RegExp(`\\b(?:${PY_KEYWORDS})\\b`, "y") },
    { kind: "number", re: /\b\d+(?:\.\d+)?\b/y },
  ],
  javascript: [
    { kind: "comment", re: /(\/\/.*|\/\*[\s\S]*?\*\/)/y },
    { kind: "string", re: /(`(?:[^`\\]|\\.)*`|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')/y },
    { kind: "func", re: /(?<=function\s)[A-Za-z_$]\w*/y },
    { kind: "keyword", re: new RegExp(`\\b(?:${JS_KEYWORDS})\\b`, "y") },
    { kind: "number", re: /\b\d+(?:\.\d+)?\b/y },
  ],
  json: [
    { kind: "string", re: /"(?:[^"\\\n]|\\.)*"/y },
    { kind: "keyword", re: /\b(?:true|false|null)\b/y },
    { kind: "number", re: /-?\b\d+(?:\.\d+)?\b/y },
  ],
  markdown: [
    { kind: "comment", re: /^#{1,6}\s.*/y },
    { kind: "code", re: /`[^`\n]+`/y },
    { kind: "bold", re: /\*\*[^*\n]+\*\*/y },
  ],
};

RULES.tsx = RULES.javascript;
RULES.ts = RULES.javascript;
RULES.jsx = RULES.javascript;
RULES.js = RULES.javascript;
RULES.md = RULES.markdown;
RULES.py = RULES.python;

/** 파일 확장자로 언어를 고른다. 모르면 `null` — 강조 없이 그대로 보여준다. */
export function langOf(path: string): string | null {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    py: "python", js: "javascript", jsx: "javascript",
    ts: "javascript", tsx: "javascript", json: "json", md: "markdown",
  };
  return map[ext] ?? null;
}

function tokenize(line: string, lang: string): Token[] {
  const rules = RULES[lang];
  if (!rules) return [{ kind: "plain", text: line }];
  const out: Token[] = [];
  let i = 0;
  while (i < line.length) {
    let matched = false;
    for (const rule of rules) {
      rule.re.lastIndex = i;
      const m = rule.re.exec(line);
      if (m && m.index === i && m[0].length > 0) {
        out.push({ kind: rule.kind, text: m[0] });
        i += m[0].length;
        matched = true;
        break;
      }
    }
    if (!matched) {
      out.push({ kind: "plain", text: line[i] });
      i += 1;
    }
  }
  return out;
}

const COLORS: Record<TokenKind, string> = {
  plain: "var(--fg)",
  comment: "var(--dim)",
  string: "var(--ok)",
  number: "var(--warn)",
  keyword: "var(--accent)",
  func: "var(--accent-2)",
  heading: "var(--accent)",
  bold: "var(--fg)",
  code: "var(--ok)",
  punct: "var(--muted)",
};

/** 한 줄을 강조된 조각들로. `lang` 이 `null` 이면 강조 없이 그대로. */
export function highlightLine(line: string, lang: string | null) {
  if (!lang || !RULES[lang]) return line;
  // 연속된 같은 종류는 하나로 합쳐 span 개수를 줄인다 — 파일이 길수록
  // DOM 노드 수가 렌더 시간에 그대로 반영된다.
  const tokens = tokenize(line, lang);
  const merged: Token[] = [];
  for (const t of tokens) {
    const last = merged[merged.length - 1];
    if (last && last.kind === t.kind) last.text += t.text;
    else merged.push({ ...t });
  }
  return merged.map((t, i) =>
    t.kind === "plain"
      ? t.text
      : <span key={i} style={{ color: COLORS[t.kind] }}>{t.text}</span>,
  );
}
