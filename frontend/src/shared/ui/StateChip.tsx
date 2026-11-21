import { Chip } from "@mui/material";
import type { ChipProps } from "@mui/material";
import { stateColor, stateLabel, type StateKind } from "../lib/stateColors";

interface StateChipProps {
  kind?: StateKind;
  state?: string | null;
  size?: ChipProps["size"];
  variant?: ChipProps["variant"];
}

export function StateChip({
  kind = "campaign",
  state,
  size = "small",
  variant = "outlined"
}: StateChipProps) {
  return (
    <Chip
      size={size}
      variant={variant}
      label={stateLabel(kind, state)}
      color={stateColor(kind, state)}
    />
  );
}
