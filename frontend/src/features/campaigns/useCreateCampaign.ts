import { useCallback, useRef, useState } from "react";
import { createCampaign } from "../../shared/api/campaigns";
import type { CampaignCreateInput, CreateCampaignResponse } from "../../shared/api/types";

export function useCreateCampaign() {
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);

  const submit = useCallback(
    async (input: CampaignCreateInput): Promise<CreateCampaignResponse> => {
      if (submittingRef.current) {
        throw new Error("Создание кампании уже выполняется");
      }
      submittingRef.current = true;
      setSubmitting(true);
      try {
        return await createCampaign(input);
      } finally {
        submittingRef.current = false;
        setSubmitting(false);
      }
    },
    []
  );

  return { submitting, submit };
}
