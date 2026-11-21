import { useState } from "react";
import type { FormEvent } from "react";
import {
  Box,
  Button,
  CircularProgress,
  DialogActions,
  DialogContent,
  Stack,
  TextField
} from "@mui/material";
import { getApiErrorCode, getErrorMessage } from "../../shared/api/client";
import type { CampaignCreateInput, OfferOption } from "../../shared/api/types";
import { useOfferSearch } from "../../shared/hooks/useOfferSearch";
import { OfferAutocomplete } from "../../shared/ui/OfferAutocomplete";
import {
  hasFormErrors,
  validateCampaignForm,
  type CampaignFormErrors
} from "./campaignFormValidation";

interface CampaignFormProps {
  submitting: boolean;
  onSubmit: (values: CampaignCreateInput) => Promise<void>;
  onCancel: () => void;
  onError?: (message: string, code?: string) => void;
}

export function CampaignForm({ submitting, onSubmit, onCancel, onError }: CampaignFormProps) {
  const [name, setName] = useState("");
  const [geo, setGeo] = useState("");
  const [offer, setOffer] = useState<OfferOption | null>(null);
  const [fieldErrors, setFieldErrors] = useState<CampaignFormErrors>({});

  const {
    query: offerQuery,
    setQuery: setOfferQuery,
    offers,
    loading: loadingOffers
  } = useOfferSearch({ onError });

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;

    const errors = validateCampaignForm({ name, geo, offer });
    setFieldErrors(errors);
    if (hasFormErrors(errors) || !offer) return;

    try {
      await onSubmit({
        name: name.trim(),
        geo: geo.trim(),
        offer_id: offer.id
      });
    } catch (error) {
      onError?.(getErrorMessage(error), getApiErrorCode(error));
    }
  };

  return (
    <Box component="form" onSubmit={handleSubmit} noValidate>
      <DialogContent dividers>
        <Stack spacing={2.5}>
          <TextField
            label="Название"
            placeholder="имя кампании"
            fullWidth
            autoFocus
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              setFieldErrors((previous) => ({ ...previous, name: undefined }));
            }}
            error={Boolean(fieldErrors.name)}
            helperText={fieldErrors.name}
            inputProps={{ maxLength: 255 }}
          />
          <TextField
            label="Код страны"
            placeholder="MX, AU, RO, ..."
            fullWidth
            value={geo}
            onChange={(event) => {
              setGeo(event.target.value);
              setFieldErrors((previous) => ({ ...previous, geo: undefined }));
            }}
            error={Boolean(fieldErrors.geo)}
            helperText={fieldErrors.geo || "Можно указать несколько ISO-кодов через запятую"}
            inputProps={{ maxLength: 255 }}
          />
          <OfferAutocomplete
            value={offer}
            query={offerQuery}
            options={offers}
            loading={loadingOffers}
            label="Предложения"
            placeholder="Поиск по офферам с автокомплитом"
            error={Boolean(fieldErrors.offer)}
            helperText={fieldErrors.offer}
            onChange={(next) => {
              setOffer(next);
              setFieldErrors((previous) => ({ ...previous, offer: undefined }));
            }}
            onQueryChange={setOfferQuery}
          />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, py: 2 }}>
        <Button onClick={onCancel} disabled={submitting}>
          Отмена
        </Button>
        <Button type="submit" variant="contained" disabled={submitting} aria-label="Создать">
          {submitting ? <CircularProgress size={22} color="inherit" /> : "Создать"}
        </Button>
      </DialogActions>
    </Box>
  );
}
