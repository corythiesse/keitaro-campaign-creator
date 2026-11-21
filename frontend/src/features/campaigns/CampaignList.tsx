import {
  Box,
  Button,
  CircularProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  Typography
} from "@mui/material";
import { Add as AddIcon } from "@mui/icons-material";
import type { CampaignSummary } from "../../shared/api/types";
import { formatDate } from "../../shared/lib/formatDate";
import { ErrorAlert } from "../../shared/ui/ErrorAlert";
import { LoadingBlock } from "../../shared/ui/LoadingBlock";
import { StateChip } from "../../shared/ui/StateChip";

function secondaryText(campaign: CampaignSummary): string {
  const created = campaign.created_at ? formatDate(campaign.created_at) : null;
  return [
    campaign.alias ? `alias ${campaign.alias}` : null,
    campaign.keitaro_id ? `Keitaro ID ${campaign.keitaro_id}` : null,
    created
  ]
    .filter(Boolean)
    .join(" · ");
}

interface EmptyStateProps {
  filtered: boolean;
  onCreate: () => void;
  onResetFilters?: () => void;
}

function EmptyState({ filtered, onCreate, onResetFilters }: EmptyStateProps) {
  return (
    <Stack alignItems="center" spacing={2} sx={{ py: 6, px: 2, textAlign: "center" }}>
      <Typography variant="subtitle1" fontWeight={600}>
        {filtered ? "Ничего не найдено" : "Пока нет кампаний"}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {filtered
          ? "Измените поисковый запрос или сбросьте фильтр статуса."
          : "Создайте первую кампанию — она появится в этом списке."}
      </Typography>
      {filtered ? (
        <Button variant="outlined" onClick={onResetFilters}>
          Сбросить фильтры
        </Button>
      ) : (
        <Button variant="outlined" startIcon={<AddIcon />} onClick={onCreate}>
          Создать кампанию
        </Button>
      )}
    </Stack>
  );
}

interface CampaignListProps {
  campaigns: CampaignSummary[];
  loading: boolean;
  error: string | null;
  hasMore: boolean;
  loadingMore: boolean;
  filtered: boolean;
  onRetry: () => void;
  onCreate: () => void;
  onOpen: (campaign: CampaignSummary) => void;
  onLoadMore: () => void;
  onResetFilters: () => void;
}

export function CampaignList({
  campaigns,
  loading,
  error,
  hasMore,
  loadingMore,
  filtered,
  onRetry,
  onCreate,
  onOpen,
  onLoadMore,
  onResetFilters
}: CampaignListProps) {
  const hasCampaigns = campaigns.length > 0;

  return (
    <Paper variant="outlined" sx={{ overflow: "hidden" }}>
      {error && hasCampaigns && <ErrorAlert message={error} onRetry={onRetry} sx={{ m: 2 }} />}
      {loading ? (
        <LoadingBlock message="Загрузка кампаний…" />
      ) : !hasCampaigns ? (
        error ? (
          <Box sx={{ p: 2 }}>
            <ErrorAlert message={error} onRetry={onRetry} />
          </Box>
        ) : (
          <EmptyState filtered={filtered} onCreate={onCreate} onResetFilters={onResetFilters} />
        )
      ) : (
        <>
          <List disablePadding>
            {campaigns.map((campaign, index) => (
              <ListItem key={campaign.id} disablePadding divider={index < campaigns.length - 1}>
                <ListItemButton
                  alignItems="flex-start"
                  onClick={() => onOpen(campaign)}
                  sx={{ gap: 2, py: 2 }}
                >
                  <ListItemText
                    primary={campaign.name}
                    secondary={secondaryText(campaign)}
                    slotProps={{
                      primary: { fontWeight: 600 },
                      secondary: { sx: { mt: 0.5 } }
                    }}
                  />
                  {campaign.state && (
                    <StateChip
                      kind="campaign"
                      state={campaign.state}
                      size="small"
                      variant="outlined"
                    />
                  )}
                </ListItemButton>
              </ListItem>
            ))}
          </List>
          {hasMore && (
            <Box sx={{ p: 2, display: "flex", justifyContent: "center" }}>
              <Button
                variant="text"
                onClick={onLoadMore}
                disabled={loadingMore}
                startIcon={loadingMore ? <CircularProgress size={18} color="inherit" /> : undefined}
              >
                {loadingMore ? "Загрузка…" : "Показать ещё"}
              </Button>
            </Box>
          )}
        </>
      )}
    </Paper>
  );
}
