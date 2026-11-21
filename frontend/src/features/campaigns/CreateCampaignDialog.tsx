import { Dialog, DialogTitle } from "@mui/material";
import type { CampaignCreateInput, CreateCampaignResponse } from "../../shared/api/types";
import { CampaignForm } from "./CampaignForm";
import { useCreateCampaign } from "./useCreateCampaign";

interface CreateCampaignDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated?: (body: CreateCampaignResponse) => void;
  onError?: (message: string, code?: string) => void;
}

export function CreateCampaignDialog({
  open,
  onClose,
  onCreated,
  onError
}: CreateCampaignDialogProps) {
  const { submitting, submit } = useCreateCampaign();

  const handleClose = () => {
    if (submitting) return; // Esc, backdrop и «Отмена» игнорируются во время отправки
    onClose();
  };

  const handleSubmit = async (values: CampaignCreateInput) => {
    const body = await submit(values);
    onCreated?.(body);
  };

  return (
    <Dialog open={open} onClose={handleClose} fullWidth maxWidth="sm">
      <DialogTitle>Создать кампанию</DialogTitle>
      <CampaignForm
        submitting={submitting}
        onSubmit={handleSubmit}
        onCancel={handleClose}
        onError={onError}
      />
    </Dialog>
  );
}
