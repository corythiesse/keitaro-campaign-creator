import { useState } from "react";
import { Button, CircularProgress, Stack } from "@mui/material";
import { Add as AddIcon } from "@mui/icons-material";
import type { OfferOption } from "../../shared/api/types";
import { useOfferSearch } from "../../shared/hooks/useOfferSearch";
import { OfferAutocomplete } from "../../shared/ui/OfferAutocomplete";

interface AddOfferFormProps {
  busy: boolean;
  onAdd: (offer: { offer_id: number; name?: string }) => Promise<unknown | null>;
  onError?: (message: string, code?: string) => void;
}

export function AddOfferForm({ busy, onAdd, onError }: AddOfferFormProps) {
  const [value, setValue] = useState<OfferOption | null>(null);
  const [searchEnabled, setSearchEnabled] = useState(false);
  const { query, setQuery, offers, loading } = useOfferSearch({
    onError,
    enabled: searchEnabled
  });

  const submit = async () => {
    if (!value || busy) return;
    const added = await onAdd({ offer_id: value.id, name: value.name });
    if (added) {
      setValue(null);
      setQuery("");
    }
  };

  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 1.5 }}>
      <OfferAutocomplete
        size="small"
        value={value}
        query={query}
        options={offers}
        loading={loading}
        label="Добавить предложение"
        placeholder="Поиск по активным офферам"
        onChange={setValue}
        onQueryChange={setQuery}
        onOpen={() => setSearchEnabled(true)}
      />
      <Button
        variant="outlined"
        startIcon={busy ? <CircularProgress size={18} /> : <AddIcon />}
        disabled={!value || busy}
        onClick={submit}
        sx={{ flexShrink: 0 }}
      >
        Добавить
      </Button>
    </Stack>
  );
}
