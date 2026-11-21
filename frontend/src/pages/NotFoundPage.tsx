import { Button, Container, Stack, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";

export function NotFoundPage({ message = "Страница не найдена" }: { message?: string }) {
  return (
    <Container maxWidth="sm" sx={{ py: 10 }}>
      <Stack spacing={2} alignItems="flex-start">
        <Typography variant="h5" fontWeight={700}>
          404
        </Typography>
        <Typography color="text.secondary">{message}</Typography>
        <Button component={RouterLink} to="/" variant="contained">
          К списку кампаний
        </Button>
      </Stack>
    </Container>
  );
}
