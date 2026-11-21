import { useCallback, useState } from "react";

export type NoticeSeverity = "success" | "info" | "warning" | "error";

export interface Notice {
  open: boolean;
  severity: NoticeSeverity;
  message: string;
}

const EMPTY_NOTICE: Notice = {
  open: false,
  severity: "success",
  message: ""
};

export function useNotice() {
  const [notice, setNotice] = useState<Notice>(EMPTY_NOTICE);

  const showNotice = useCallback((severity: NoticeSeverity, message: string) => {
    setNotice({ open: true, severity, message });
  }, []);

  const closeNotice = useCallback(() => {
    setNotice((previous) => ({ ...previous, open: false }));
  }, []);

  return { notice, showNotice, closeNotice };
}
