import { Alert, Stack, Typography } from "@mui/material";
import type { Offer, OfferPatch, Stream } from "../../shared/api/types";
import { StreamItem } from "./StreamItem";

interface StreamListProps {
  streams: Stream[];
  busy: boolean;
  busyFor: (offer: Offer) => boolean;
  onOfferPatch: (offer: Offer, patch: OfferPatch) => void;
  onAddOffer: (
    stream: Stream,
    offer: { offer_id: number; name?: string }
  ) => Promise<unknown | null>;
  onError?: (message: string, code?: string) => void;
}

export function StreamList({
  streams,
  busy,
  busyFor,
  onOfferPatch,
  onAddOffer,
  onError
}: StreamListProps) {
  if (streams.length === 0) {
    return (
      <Alert severity="info">
        У кампании нет потоков. Нажмите «Загрузить из Keitaro», чтобы получить их.
      </Alert>
    );
  }

  return (
    <Stack spacing={2}>
      {streams.map((stream) => (
        <StreamItem
          key={stream.id}
          stream={stream}
          busy={busy}
          busyFor={busyFor}
          onOfferPatch={onOfferPatch}
          onAddOffer={onAddOffer}
          onError={onError}
        />
      ))}
      <Typography variant="caption" color="text.secondary">
        Удалённые предложения остаются в локальной базе и могут быть восстановлены. Состояние
        потоков синхронизируется из Keitaro.
      </Typography>
    </Stack>
  );
}
