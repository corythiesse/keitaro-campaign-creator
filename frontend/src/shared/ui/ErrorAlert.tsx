import type { ReactNode } from "react";
import { Alert, Button } from "@mui/material";
import type { SxProps, Theme } from "@mui/material";

interface ErrorAlertProps {
  message: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  sx?: SxProps<Theme>;
}

export function ErrorAlert({ message, onRetry, retryLabel = "Повторить", sx }: ErrorAlertProps) {
  return (
    <Alert
      severity="error"
      sx={sx}
      action={
        onRetry ? (
          <Button color="inherit" size="small" onClick={onRetry}>
            {retryLabel}
          </Button>
        ) : undefined
      }
    >
      {message}
    </Alert>
  );
}
