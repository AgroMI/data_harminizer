export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function formatNumber(value: number | null | undefined, fallback = "n/a"): string {
  if (value === null || value === undefined) return fallback;
  return parseFloat(value.toFixed(2)).toString();
}

export function readOnlyText(value: string | null | undefined, fallback = "n/a"): string {
  if (!value) {
    return fallback;
  }
  return value;
}

export async function readProblemDetail(response: Response, fallback: string): Promise<string> {
  const problem = (await response.json().catch(() => null)) as { detail?: string } | null;
  return problem?.detail || fallback;
}
