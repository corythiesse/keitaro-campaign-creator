import { Alert, Snackbar } from "@mui/material";
import type { Notice } from "../hooks/useNotice";
import { NOTICE_DURATION_MS } from "../lib/constants";

interface NoticeSnackbarProps {
  notice: Notice;
  onClose: () => void;
  duration?: number;
}

export function NoticeSnackbar({
  notice,
  onClose,
  duration = NOTICE_DURATION_MS
}: NoticeSnackbarProps) {
  return (
    <Snackbar open={notice.open} autoHideDuration={duration} onClose={onClose}>
      <Alert severity={notice.severity} onClose={onClose} sx={{ width: "100%" }}>
        {notice.message}
      </Alert>
    </Snackbar>
  );
}
