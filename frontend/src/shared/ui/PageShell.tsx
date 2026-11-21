import type { ReactNode } from "react";
import { Container, Stack } from "@mui/material";

interface PageShellProps {
  header: ReactNode;
  children: ReactNode;
  maxWidth?: "sm" | "md" | "lg";
}

export function PageShell({ header, children, maxWidth = "md" }: PageShellProps) {
  return (
    <Container maxWidth={maxWidth} sx={{ py: 7 }}>
      <Stack spacing={3}>
        {header}
        {children}
      </Stack>
    </Container>
  );
}
