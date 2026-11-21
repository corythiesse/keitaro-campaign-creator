import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as campaignsApi from "../shared/api/campaigns";
import { ApiError } from "../shared/api/client";
import * as offersApi from "../shared/api/offers";
import { makeCampaignSummary } from "../test/fixtures";
import { CampaignsPage } from "./CampaignsPage";

vi.mock("../shared/api/campaigns", () => ({
  CAMPAIGNS_PAGE_SIZE: 50,
  fetchCampaigns: vi.fn(),
  createCampaign: vi.fn()
}));

vi.mock("../shared/api/offers", () => ({
  searchOffers: vi.fn()
}));

const fetchCampaigns = vi.mocked(campaignsApi.fetchCampaigns);
const createCampaign = vi.mocked(campaignsApi.createCampaign);
const searchOffers = vi.mocked(offersApi.searchOffers);

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<CampaignsPage />} />
        <Route path="/campaigns/:campaignId" element={<div>Редактор кампании</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  fetchCampaigns.mockResolvedValue([makeCampaignSummary()]);
  searchOffers.mockResolvedValue([]);
});

describe("CampaignsPage", () => {
  it("renders campaigns loaded from the API", async () => {
    renderPage();

    expect(await screen.findByText("Test campaign")).toBeInTheDocument();
    expect(screen.getByText(/alias test_alias/)).toBeInTheDocument();
    expect(screen.getByText("Активна")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    fetchCampaigns.mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("Пока нет кампаний")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Создать кампанию" })).toBeInTheDocument();
  });

  it("shows a load error and retries", async () => {
    const user = userEvent.setup();
    fetchCampaigns.mockRejectedValueOnce(new Error("Сервер недоступен"));

    renderPage();

    expect(await screen.findByText("Сервер недоступен")).toBeInTheDocument();
    fetchCampaigns.mockResolvedValueOnce([makeCampaignSummary()]);
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("Test campaign")).toBeInTheDocument();
  });

  it("debounces the search query", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Test campaign");

    await user.type(screen.getByLabelText("Поиск"), "sale");

    await waitFor(
      () => {
        expect(fetchCampaigns).toHaveBeenCalledWith(
          expect.objectContaining({ q: "sale", offset: 0 })
        );
      },
      { timeout: 1500 }
    );
  });

  it("loads the next page with offset", async () => {
    const user = userEvent.setup();
    const firstPage = Array.from({ length: 50 }, (_, index) =>
      makeCampaignSummary({ id: index + 1, name: `Campaign ${index + 1}` })
    );
    const secondPage = Array.from({ length: 10 }, (_, index) =>
      makeCampaignSummary({ id: index + 51, name: `Campaign ${index + 51}` })
    );
    fetchCampaigns.mockResolvedValueOnce(firstPage).mockResolvedValueOnce(secondPage);

    renderPage();
    await screen.findByText("Campaign 1");

    await user.click(screen.getByRole("button", { name: "Показать ещё" }));

    expect(await screen.findByText("Campaign 51")).toBeInTheDocument();
    expect(fetchCampaigns).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 50 }));
  });

  it("opens the create dialog", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Test campaign");

    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByText("Создать кампанию")).toBeInTheDocument();
  });

  it("navigates to the editor by local campaign id", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText("Test campaign"));

    expect(await screen.findByText("Редактор кампании")).toBeInTheDocument();
  });

  it("shows a filtered empty state and resets filters", async () => {
    const user = userEvent.setup();
    fetchCampaigns.mockResolvedValueOnce([makeCampaignSummary()]).mockResolvedValueOnce([]);

    renderPage();
    await screen.findByText("Test campaign");
    await user.type(screen.getByLabelText("Поиск"), "missing");

    expect(await screen.findByText("Ничего не найдено")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Сбросить фильтры" }));

    expect(await screen.findByText("Test campaign")).toBeInTheDocument();
    expect(screen.getByLabelText("Поиск")).toHaveValue("");
  });

  it("refreshes the list after PARTIAL_CREATION", async () => {
    const user = userEvent.setup();
    searchOffers.mockResolvedValue([{ id: 44, name: "Offer D" }]);
    createCampaign.mockRejectedValueOnce(
      new ApiError("Кампания создана частично", { code: "PARTIAL_CREATION" })
    );

    renderPage();
    await screen.findByText("Test campaign");
    await user.click(screen.getByRole("button", { name: "Создать" }));

    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Название"), "Partial campaign");
    await user.type(within(dialog).getByLabelText("Код страны"), "MX");
    await user.type(within(dialog).getByLabelText("Предложения"), "Offer");
    await user.click(await screen.findByText("Offer D (ID: 44)"));
    await user.click(within(dialog).getByRole("button", { name: "Создать" }));

    expect(await screen.findByText("Кампания создана частично")).toBeInTheDocument();
    await waitFor(() => expect(fetchCampaigns.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it("creates a campaign and refreshes the list", async () => {
    const user = userEvent.setup();
    searchOffers.mockResolvedValue([{ id: 44, name: "Offer D" }]);
    createCampaign.mockResolvedValue({
      success: true,
      campaign: { id: 2, name: "New campaign" },
      streams: []
    });

    renderPage();
    await screen.findByText("Test campaign");
    await user.click(screen.getByRole("button", { name: "Создать" }));

    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Название"), "New campaign");
    await user.type(within(dialog).getByLabelText("Код страны"), "MX");
    await user.type(within(dialog).getByLabelText("Предложения"), "Offer");
    await user.click(await screen.findByText("Offer D (ID: 44)"));
    await user.click(within(dialog).getByRole("button", { name: "Создать" }));

    await waitFor(() => {
      expect(createCampaign).toHaveBeenCalledWith({
        name: "New campaign",
        geo: "MX",
        offer_id: 44
      });
    });
    expect(await screen.findByText(/Кампания создана: New campaign/)).toBeInTheDocument();
    await waitFor(() => expect(fetchCampaigns.mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});
