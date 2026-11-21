import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { Alert, Button, Container, Stack, Typography } from "@mui/material";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    message: ""
  };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : "Неизвестная ошибка"
    };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error("Unhandled UI error", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <Container maxWidth="sm" sx={{ py: 10 }}>
        <Stack spacing={2}>
          <Typography variant="h5" fontWeight={700}>
            Что-то пошло не так
          </Typography>
          <Alert severity="error">{this.state.message}</Alert>
          <Button variant="contained" onClick={() => window.location.reload()}>
            Перезагрузить страницу
          </Button>
        </Stack>
      </Container>
    );
  }
}
