import { Box } from "@mui/material";
import type { Offer, OfferPatch } from "../../shared/api/types";
import { OfferRow } from "./OfferRow";

interface OfferListProps {
  offers: Offer[];
  busyFor: (offer: Offer) => boolean;
  onOfferPatch: (offer: Offer, patch: OfferPatch) => void;
}

export function OfferList({ offers, busyFor, onOfferPatch }: OfferListProps) {
  return (
    <Box sx={{ mt: 1.5 }}>
      {offers.map((offer) => (
        <OfferRow
          key={offer.id}
          offer={offer}
          busy={busyFor(offer)}
          onPatch={(patch) => onOfferPatch(offer, patch)}
        />
      ))}
    </Box>
  );
}
