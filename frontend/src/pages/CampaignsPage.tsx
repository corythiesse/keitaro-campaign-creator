import { useState } from "react";
import { Box, Button, LinearProgress, Stack, Typography } from "@mui/material";
import { Add as AddIcon } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { CampaignFilters } from "../features/campaigns/CampaignFilters";
import { CampaignList } from "../features/campaigns/CampaignList";
import { CreateCampaignDialog } from "../features/campaigns/CreateCampaignDialog";
import { useCampaigns } from "../features/campaigns/useCampaigns";
import type { CampaignSummary, CreateCampaignResponse } from "../shared/api/types";
import { useNotice } from "../shared/hooks/useNotice";
import { NoticeSnackbar } from "../shared/ui/NoticeSnackbar";
import { PageShell } from "../shared/ui/PageShell";

export function CampaignsPage() {
  const campaignsState = useCampaigns();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formKey, setFormKey] = useState(0);
  const { notice, showNotice, closeNotice } = useNotice();
  const navigate = useNavigate();

  const handleOpenDialog = () => {
    setFormKey((key) => key + 1); // remount формы: каждое открытие — с чистых полей
    setDialogOpen(true);
  };

  const handleCreated = (body: CreateCampaignResponse) => {
    const campaign = body.campaign;
    setDialogOpen(false);
    showNotice(
      "success",
      `Кампания создана: ${campaign?.name || "кампания"} (ID ${campaign?.id ?? "—"})`
    );
    campaignsState.refresh();
  };

  const handleFormError = (message: string, code?: string) => {
    showNotice("error", message);
    // PARTIAL_CREATION: кампания уже сохранена локально — обновляем список.
    if (code === "PARTIAL_CREATION") campaignsState.refresh();
  };

  const handleOpenCampaign = (campaign: CampaignSummary) => {
    navigate(`/campaigns/${campaign.id}`);
  };

  const resetFilters = () => {
    campaignsState.setQuery("");
    campaignsState.setStateFilter("");
  };

  return (
    <PageShell
      maxWidth="md"
      header={
        <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
          <Typography variant="h6" fontWeight={700}>
            Кампании
          </Typography>
          <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpenDialog}>
            Создать
          </Button>
        </Stack>
      }
    >
      <Box sx={{ minHeight: 4 }}>{campaignsState.refreshing && <LinearProgress />}</Box>

      <CampaignFilters
        query={campaignsState.query}
        stateFilter={campaignsState.stateFilter}
        onQueryChange={campaignsState.setQuery}
        onStateChange={campaignsState.setStateFilter}
      />

      <CampaignList
        campaigns={campaignsState.campaigns}
        loading={campaignsState.loading}
        error={campaignsState.error}
        hasMore={campaignsState.hasMore}
        loadingMore={campaignsState.loadingMore}
        filtered={campaignsState.hasFilters}
        onRetry={campaignsState.retry}
        onCreate={handleOpenDialog}
        onOpen={handleOpenCampaign}
        onLoadMore={campaignsState.loadMore}
        onResetFilters={resetFilters}
      />

      <CreateCampaignDialog
        key={formKey}
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={handleCreated}
        onError={handleFormError}
      />

      <NoticeSnackbar notice={notice} onClose={closeNotice} />
    </PageShell>
  );
}
