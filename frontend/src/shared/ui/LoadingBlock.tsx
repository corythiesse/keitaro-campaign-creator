import { CircularProgress, Stack, Typography } from "@mui/material";

interface LoadingBlockProps {
  message: string;
  size?: number;
}

export function LoadingBlock({ message, size = 28 }: LoadingBlockProps) {
  return (
    <Stack alignItems="center" spacing={2} sx={{ py: 6, px: 2 }}>
      <CircularProgress size={size} />
      <Typography variant="body2" color="text.secondary">
        {message}
      </Typography>
    </Stack>
  );
}
