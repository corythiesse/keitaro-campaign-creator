import { Button, Chip, CircularProgress, Stack, Typography } from "@mui/material";
import {
  CloudDownload as CloudDownloadIcon,
  CloudUpload as CloudUploadIcon,
  Undo as UndoIcon
} from "@mui/icons-material";
import type { CampaignEditor } from "../../shared/api/types";
import { formatDate } from "../../shared/lib/formatDate";

interface SyncToolbarProps {
  campaign: CampaignEditor | null;
  busy: string | null;
  onLoad: () => void;
  onPush: () => void;
  onDiscard: () => void;
}

export function SyncToolbar({ campaign, busy, onLoad, onPush, onDiscard }: SyncToolbarProps) {
  const hasChanges = Boolean(campaign?.has_local_changes);
  const disabled = Boolean(busy);

  return (
    <Stack spacing={1.5}>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1.5}
        alignItems={{ sm: "center" }}
        flexWrap="wrap"
      >
        <Button
          variant="outlined"
          startIcon={busy === "load" ? <CircularProgress size={18} /> : <CloudDownloadIcon />}
          disabled={disabled}
          onClick={onLoad}
          title="Загрузить информацию о потоках и предложениях из Keitaro"
        >
          Загрузить из Keitaro
        </Button>
        <Button
          variant="contained"
          startIcon={
            busy === "push" ? <CircularProgress size={18} color="inherit" /> : <CloudUploadIcon />
          }
          disabled={!hasChanges || disabled}
          onClick={onPush}
        >
          Отправить изменения в Keitaro
        </Button>
        <Button
          variant="text"
          startIcon={busy === "discard" ? <CircularProgress size={18} /> : <UndoIcon />}
          disabled={!hasChanges || disabled}
          onClick={onDiscard}
        >
          Отменить изменения
        </Button>
      </Stack>

      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        {hasChanges && (
          <Chip color="warning" size="small" label="Есть несинхронизированные изменения" />
        )}
        {!hasChanges && campaign?.last_pushed_at && (
          <Chip color="success" size="small" label="Синхронизировано с Keitaro" />
        )}
        <Typography variant="caption" color="text.secondary">
          Загружено: {formatDate(campaign?.last_loaded_at)} · Отправлено:{" "}
          {formatDate(campaign?.last_pushed_at)}
          {campaign?.revision != null ? ` · revision ${campaign.revision}` : ""}
        </Typography>
      </Stack>

      {campaign?.last_sync_error && (
        <Typography variant="caption" color="error.main">
          Последняя ошибка синхронизации: {campaign.last_sync_error}
        </Typography>
      )}
    </Stack>
  );
}
