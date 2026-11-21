import { InputAdornment, MenuItem, Stack, TextField } from "@mui/material";
import { Search as SearchIcon } from "@mui/icons-material";

const STATE_OPTIONS = [
  { value: "", label: "Все статусы" },
  { value: "active", label: "Активные" },
  { value: "suspended", label: "Приостановленные" },
  { value: "paused", label: "На паузе" },
  { value: "deleted", label: "Удалённые" },
  { value: "archived", label: "В архиве" },
  { value: "disabled", label: "Отключённые" }
];

interface CampaignFiltersProps {
  query: string;
  stateFilter: string;
  onQueryChange: (query: string) => void;
  onStateChange: (state: string) => void;
}

export function CampaignFilters({
  query,
  stateFilter,
  onQueryChange,
  onStateChange
}: CampaignFiltersProps) {
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
      <TextField
        size="small"
        fullWidth
        label="Поиск"
        placeholder="Название или alias"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <SearchIcon fontSize="small" />
            </InputAdornment>
          )
        }}
      />
      <TextField
        select
        size="small"
        label="Статус"
        value={stateFilter}
        onChange={(event) => onStateChange(event.target.value)}
        sx={{ minWidth: { sm: 210 } }}
      >
        {STATE_OPTIONS.map((option) => (
          <MenuItem key={option.value || "all"} value={option.value}>
            {option.label}
          </MenuItem>
        ))}
      </TextField>
    </Stack>
  );
}
