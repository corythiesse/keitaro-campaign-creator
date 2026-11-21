import { Autocomplete, CircularProgress, TextField } from "@mui/material";
import type { ReactNode } from "react";
import type { OfferOption } from "../api/types";

interface OfferAutocompleteProps {
  value: OfferOption | null;
  query: string;
  options: OfferOption[];
  loading: boolean;
  label: string;
  placeholder?: string;
  error?: boolean;
  helperText?: ReactNode;
  size?: "small" | "medium";
  onChange: (value: OfferOption | null) => void;
  onQueryChange: (query: string) => void;
  onOpen?: () => void;
}

export function OfferAutocomplete({
  value,
  query,
  options,
  loading,
  label,
  placeholder,
  error = false,
  helperText,
  size = "medium",
  onChange,
  onQueryChange,
  onOpen
}: OfferAutocompleteProps) {
  return (
    <Autocomplete
      size={size}
      fullWidth
      options={options}
      value={value}
      inputValue={query}
      loading={loading}
      getOptionLabel={(option) => `${option.name} (ID: ${option.id})`}
      isOptionEqualToValue={(left, right) => left.id === right.id}
      onInputChange={(_, next) => {
        // Do not drop the label after selection/reset: the controlled input
        // would otherwise keep showing the typed search string.
        onOpen?.();
        onQueryChange(next);
      }}
      onChange={(_, next) => onChange(next)}
      onOpen={onOpen}
      noOptionsText="Активные офферы не найдены"
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder={placeholder}
          error={error}
          helperText={helperText}
          InputProps={{
            ...params.InputProps,
            endAdornment: (
              <>
                {loading ? (
                  <CircularProgress color="inherit" size={size === "small" ? 16 : 18} />
                ) : null}
                {params.InputProps.endAdornment}
              </>
            )
          }}
        />
      )}
    />
  );
}
