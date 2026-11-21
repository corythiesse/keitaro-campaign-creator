import { Route, Routes } from "react-router-dom";
import { CampaignEditorPage } from "../pages/CampaignEditorPage";
import { CampaignsPage } from "../pages/CampaignsPage";
import { NotFoundPage } from "../pages/NotFoundPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<CampaignsPage />} />
      <Route path="/campaigns/:campaignId" element={<CampaignEditorPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
