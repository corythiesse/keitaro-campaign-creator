import { Box, Chip, Paper, Stack, Typography } from "@mui/material";
import type { Offer, OfferPatch, Stream } from "../../shared/api/types";
import { StateChip } from "../../shared/ui/StateChip";
import { AddOfferForm } from "./AddOfferForm";
import { OfferList } from "./OfferList";

function summary(stream: Stream): string {
  if (stream.comments) return stream.comments;
  return [stream.type, stream.schema, stream.action_payload].filter(Boolean).join(" · ");
}

function isRedirectStream(stream: Stream): boolean {
  return (stream.schema || "").trim().toLowerCase() === "redirect";
}

interface StreamItemProps {
  stream: Stream;
  busy: boolean;
  busyFor: (offer: Offer) => boolean;
  onOfferPatch: (offer: Offer, patch: OfferPatch) => void;
  onAddOffer: (
    stream: Stream,
    offer: { offer_id: number; name?: string }
  ) => Promise<unknown | null>;
  onError?: (message: string, code?: string) => void;
}

export function StreamItem({
  stream,
  busy,
  busyFor,
  onOfferPatch,
  onAddOffer,
  onError
}: StreamItemProps) {
  const isDeleted = Boolean(stream.is_deleted);
  const isRedirect = isRedirectStream(stream);

  return (
    <Paper variant="outlined" sx={{ p: 2, opacity: isDeleted ? 0.65 : 1 }}>
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography
              fontWeight={600}
              sx={{ textDecoration: isDeleted ? "line-through" : "none" }}
            >
              {stream.name}
            </Typography>
            <StateChip kind="stream" state={stream.state} size="small" variant="outlined" />
            {isDeleted && (stream.state ?? "").toLowerCase() !== "deleted" && (
              <Chip size="small" color="error" label="Удалён" />
            )}
            {stream.origin === "local" && <Chip size="small" label="Локальный" />}
          </Stack>
          {summary(stream) && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {summary(stream)}
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary">
            Keitaro ID: {stream.keitaro_id}
            {stream.offers.length > 0 ? ` · предложений: ${stream.offers.length}` : ""}
          </Typography>
        </Box>
      </Stack>

      {stream.offers.length > 0 && (
        <OfferList offers={stream.offers} busyFor={busyFor} onOfferPatch={onOfferPatch} />
      )}

      {!isDeleted && !isRedirect && (
        <AddOfferForm busy={busy} onError={onError} onAdd={(offer) => onAddOffer(stream, offer)} />
      )}
    </Paper>
  );
}
