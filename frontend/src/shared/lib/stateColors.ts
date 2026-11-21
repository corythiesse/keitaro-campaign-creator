import type { ChipProps } from "@mui/material";

export type ChipColor = ChipProps["color"];
export type StateKind = "campaign" | "offer" | "stream";

const COLORS: Record<StateKind, Record<string, ChipColor>> = {
  campaign: {
    active: "success",
    suspended: "warning",
    paused: "warning",
    deleted: "error",
    archived: "error",
    disabled: "default"
  },
  offer: {
    active: "success",
    disabled: "default",
    deleted: "error",
    archived: "default"
  },
  stream: {
    active: "success",
    disabled: "default",
    deleted: "error",
    archived: "default"
  }
};

const LABELS: Record<StateKind, Record<string, string>> = {
  campaign: {
    active: "Активна",
    suspended: "Приостановлена",
    paused: "На паузе",
    deleted: "Удалена",
    archived: "В архиве",
    disabled: "Отключена"
  },
  offer: {
    active: "Активен",
    suspended: "Приостановлен",
    paused: "На паузе",
    deleted: "Удалён",
    archived: "В архиве",
    disabled: "Отключён"
  },
  stream: {
    active: "Активен",
    suspended: "Приостановлен",
    paused: "На паузе",
    deleted: "Удалён",
    archived: "В архиве",
    disabled: "Отключён"
  }
};

export function stateColor(kind: StateKind, state: string | null | undefined): ChipColor {
  if (!state) return "default";
  return COLORS[kind][state.toLowerCase()] ?? "default";
}

export function stateLabel(kind: StateKind, state: string | null | undefined): string {
  if (!state) return "Неизвестно";
  return LABELS[kind][state.toLowerCase()] ?? state;
}
