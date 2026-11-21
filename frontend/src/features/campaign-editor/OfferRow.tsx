import { useState } from "react";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import {
  DeleteOutline as DeleteOutlineIcon,
  PushPin as PushPinIcon,
  RestoreFromTrash as RestoreIcon
} from "@mui/icons-material";
import type { Offer, OfferPatch } from "../../shared/api/types";
import { PIN_MAX, PIN_MIN } from "../../shared/lib/constants";
import { StateChip } from "../../shared/ui/StateChip";

interface OfferRowProps {
  offer: Offer;
  busy: boolean;
  onPatch: (patch: OfferPatch) => void;
}

export function OfferRow({ offer, busy, onPatch }: OfferRowProps) {
  const [pinOpen, setPinOpen] = useState(false);
  const [pinValue, setPinValue] = useState(String(offer.pinned_share ?? offer.share ?? ""));
  const [pinError, setPinError] = useState<string | null>(null);

  const normalizedState = (offer.state ?? "").toLowerCase();
  const inactive = offer.is_deleted || (normalizedState.length > 0 && normalizedState !== "active");

  const openPinDialog = () => {
    setPinValue(String(offer.pinned_share ?? offer.share ?? ""));
    setPinError(null);
    setPinOpen(true);
  };

  const submitPin = () => {
    const trimmed = pinValue.trim();
    if (!/^\d+$/.test(trimmed)) {
      setPinError("Введите целое число от 0 до 100");
      return;
    }
    const parsed = Number.parseInt(trimmed, 10);
    if (parsed < PIN_MIN || parsed > PIN_MAX) {
      setPinError("Введите целое число от 0 до 100");
      return;
    }
    setPinError(null);
    setPinOpen(false);
    onPatch({ is_pinned: true, pinned_share: parsed });
  };

  return (
    <Stack
      direction="row"
      spacing={1.5}
      alignItems="center"
      sx={{
        py: 1,
        px: 1,
        opacity: inactive ? 0.55 : 1,
        borderTop: "1px solid",
        borderColor: "divider"
      }}
    >
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Typography
          variant="body2"
          fontWeight={500}
          sx={{ textDecoration: inactive ? "line-through" : "none" }}
        >
          {offer.name || `Offer #${offer.keitaro_id}`}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Keitaro ID: {offer.keitaro_id}
          {offer.keitaro_offer_stream_id
            ? ` · OfferStream ID: ${offer.keitaro_offer_stream_id}`
            : ""}
        </Typography>
      </Box>

      <Chip
        size="small"
        variant="outlined"
        color={offer.is_pinned ? "primary" : "default"}
        icon={offer.is_pinned ? <PushPinIcon /> : undefined}
        label={`${offer.share ?? 0}%`}
        title={
          offer.is_pinned
            ? `Закреплённый вес: ${offer.pinned_share}%`
            : "Вес рассчитывается автоматически"
        }
      />
      <StateChip kind="offer" state={offer.state} size="small" variant="outlined" />

      <Tooltip describeChild title={offer.is_pinned ? "Снять закрепление" : "Закрепить вес"}>
        <span>
          <IconButton
            size="small"
            disabled={busy}
            aria-label={offer.is_pinned ? "Снять закрепление" : "Закрепить вес"}
            onClick={() => (offer.is_pinned ? onPatch({ is_pinned: false }) : openPinDialog())}
          >
            <PushPinIcon fontSize="small" color={offer.is_pinned ? "primary" : "inherit"} />
          </IconButton>
        </span>
      </Tooltip>

      <Tooltip
        describeChild
        title={offer.is_deleted ? "Восстановить предложение" : "Удалить предложение"}
      >
        <span>
          <IconButton
            size="small"
            disabled={busy}
            aria-label={offer.is_deleted ? "Восстановить предложение" : "Удалить предложение"}
            onClick={() => onPatch({ is_deleted: !offer.is_deleted })}
          >
            {offer.is_deleted ? (
              <RestoreIcon fontSize="small" />
            ) : (
              <DeleteOutlineIcon fontSize="small" />
            )}
          </IconButton>
        </span>
      </Tooltip>

      <Dialog open={pinOpen} onClose={() => setPinOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Закрепить вес предложения</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            type="number"
            label="Вес, %"
            value={pinValue}
            onChange={(event) => {
              setPinValue(event.target.value);
              setPinError(null);
            }}
            error={Boolean(pinError)}
            inputProps={{ min: PIN_MIN, max: PIN_MAX, step: 1 }}
            helperText={
              pinError ?? "Закреплённый вес не меняется при пересчёте остальных предложений"
            }
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPinOpen(false)}>Отмена</Button>
          <Button variant="contained" onClick={submitPin}>
            Закрепить
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
