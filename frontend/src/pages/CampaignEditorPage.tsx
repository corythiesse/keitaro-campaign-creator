import { Alert, Box, Button, Chip, LinearProgress, Stack, Typography } from "@mui/material";
import {
  ArrowBack as ArrowBackIcon,
  OpenInNew as OpenInNewIcon,
  Refresh as RefreshIcon
} from "@mui/icons-material";
import { Link as RouterLink, useParams } from "react-router-dom";
import { ConfirmDialog } from "../features/campaign-editor/ConfirmDialog";
import { StreamList } from "../features/campaign-editor/StreamList";
import { SyncToolbar } from "../features/campaign-editor/SyncToolbar";
import { useCampaignEditor } from "../features/campaign-editor/useCampaignEditor";
import { ErrorAlert } from "../shared/ui/ErrorAlert";
import { LoadingBlock } from "../shared/ui/LoadingBlock";
import { NoticeSnackbar } from "../shared/ui/NoticeSnackbar";
import { PageShell } from "../shared/ui/PageShell";
import { StateChip } from "../shared/ui/StateChip";
import { NotFoundPage } from "./NotFoundPage";

function CampaignEditorView({ campaignId }: { campaignId: string }) {
  const editor = useCampaignEditor(campaignId);
  const { campaign } = editor;
  const failedResults = editor.pushResults.filter((result) => result.status === "error");

  const confirmContent =
    editor.confirm === "load"
      ? {
          title: "Потерять несинхронизированные изменения?",
          body: "Загрузка из Keitaro заменит текущее локальное состояние последней версией из Keitaro. Несинхронизированные изменения будут потеряны.",
          action: "Загрузить",
          color: "primary" as const
        }
      : {
          title: "Отменить изменения?",
          body: "Локальные изменения будут восстановлены из последней загруженной или отправленной версии Keitaro. Локально добавленные предложения будут удалены.",
          action: "Отменить изменения",
          color: "warning" as const
        };

  return (
    <PageShell
      maxWidth="lg"
      header={
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Button component={RouterLink} to="/" startIcon={<ArrowBackIcon />} size="small">
            К списку кампаний
          </Button>
          {campaign && (
            <>
              <Typography variant="h6" fontWeight={700}>
                {campaign.name}
              </Typography>
              {campaign.state && <StateChip kind="campaign" state={campaign.state} size="small" />}
              <Chip size="small" variant="outlined" label={`Keitaro ID: ${campaign.keitaro_id}`} />
              {campaign.keitaro_campaign_url && (
                <Button
                  component="a"
                  href={campaign.keitaro_campaign_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  size="small"
                  startIcon={<OpenInNewIcon />}
                >
                  Открыть в Keitaro
                </Button>
              )}
            </>
          )}
        </Stack>
      }
    >
      {campaign && (
        <SyncToolbar
          campaign={campaign}
          busy={editor.busy}
          onLoad={editor.requestLoad}
          onPush={editor.handlePush}
          onDiscard={editor.requestDiscard}
        />
      )}

      {editor.busy && <LinearProgress />}

      {editor.revisionConflict && (
        <Alert
          severity="warning"
          action={
            <Button
              color="inherit"
              size="small"
              startIcon={<RefreshIcon />}
              onClick={editor.refreshAfterConflict}
            >
              Обновить
            </Button>
          }
        >
          Данные изменились в другой вкладке. Обновите данные, чтобы продолжить.
        </Alert>
      )}

      {failedResults.length > 0 && (
        <Alert severity="warning">
          <Stack spacing={0.5}>
            <Typography variant="subtitle2">Часть потоков не удалось отправить</Typography>
            {failedResults.map((result) => (
              <Typography key={`${result.stream_id}-${result.code}`} variant="body2">
                Поток {result.keitaro_id ?? result.stream_id}: {result.code}
                {result.message ? ` — ${result.message}` : ""}
              </Typography>
            ))}
            <Box>
              <Button size="small" onClick={editor.handlePush} disabled={Boolean(editor.busy)}>
                Повторить отправку
              </Button>
            </Box>
          </Stack>
        </Alert>
      )}

      {editor.loading ? (
        <LoadingBlock message="Загрузка кампании…" />
      ) : editor.error ? (
        <ErrorAlert message={editor.error} onRetry={editor.retryLoad} />
      ) : campaign ? (
        <StreamList
          streams={campaign.streams}
          busy={Boolean(editor.busy)}
          busyFor={(offer) => editor.busy === `offer:${offer.id}`}
          onOfferPatch={editor.handleOfferPatch}
          onAddOffer={editor.handleAddOffer}
          onError={editor.showError}
        />
      ) : null}

      <ConfirmDialog
        open={Boolean(editor.confirm)}
        title={confirmContent.title}
        body={confirmContent.body}
        confirmLabel={confirmContent.action}
        confirmColor={confirmContent.color}
        onConfirm={editor.confirm === "load" ? editor.confirmLoad : editor.confirmDiscard}
        onCancel={editor.closeConfirm}
      />

      <NoticeSnackbar notice={editor.notice} onClose={editor.closeNotice} />
    </PageShell>
  );
}

export function CampaignEditorPage() {
  const { campaignId } = useParams();

  if (!campaignId || !/^\d+$/.test(campaignId)) {
    return <NotFoundPage message="Кампания не найдена" />;
  }

  return <CampaignEditorView campaignId={campaignId} />;
}
