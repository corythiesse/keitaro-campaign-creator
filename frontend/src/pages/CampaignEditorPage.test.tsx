import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as campaignsApi from "../shared/api/campaigns";
import { ApiError } from "../shared/api/client";
import * as offersApi from "../shared/api/offers";
import { makeCampaign, makeOffer, makeStream } from "../test/fixtures";
import { CampaignEditorPage } from "./CampaignEditorPage";

vi.mock("../shared/api/campaigns", () => ({
  CAMPAIGNS_PAGE_SIZE: 50,
  addOffer: vi.fn(),
  createCampaign: vi.fn(),
  discardCampaignChanges: vi.fn(),
  fetchCampaignDetail: vi.fn(),
  fetchCampaigns: vi.fn(),
  loadCampaignStreams: vi.fn(),
  pushCampaignChanges: vi.fn(),
  updateOffer: vi.fn()
}));

vi.mock("../shared/api/offers", () => ({
  searchOffers: vi.fn()
}));

const fetchCampaignDetail = vi.mocked(campaignsApi.fetchCampaignDetail);
const updateOffer = vi.mocked(campaignsApi.updateOffer);
const addOffer = vi.mocked(campaignsApi.addOffer);
const loadCampaignStreams = vi.mocked(campaignsApi.loadCampaignStreams);
const discardCampaignChanges = vi.mocked(campaignsApi.discardCampaignChanges);
const pushCampaignChanges = vi.mocked(campaignsApi.pushCampaignChanges);
const searchOffers = vi.mocked(offersApi.searchOffers);

function renderEditor(campaignId = "1") {
  return render(
    <MemoryRouter initialEntries={[`/campaigns/${campaignId}`]}>
      <Routes>
        <Route path="/campaigns/:campaignId" element={<CampaignEditorPage />} />
        <Route path="/" element={<div>Список кампаний</div>} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  fetchCampaignDetail.mockResolvedValue(makeCampaign());
  updateOffer.mockResolvedValue(makeCampaign());
  addOffer.mockResolvedValue(makeCampaign());
  loadCampaignStreams.mockResolvedValue(makeCampaign());
  discardCampaignChanges.mockResolvedValue(makeCampaign());
  pushCampaignChanges.mockResolvedValue({
    success: true,
    campaign: makeCampaign({
      has_local_changes: false,
      last_pushed_at: "2026-11-21T10:00:00Z"
    }),
    results: []
  });
  searchOffers.mockResolvedValue([{ id: 44, name: "Offer D" }]);
});

describe("CampaignEditorPage", () => {
  it("renders streams, offers and marks deleted rows as inactive", async () => {
    fetchCampaignDetail.mockResolvedValue(
      makeCampaign({
        streams: [
          makeStream({
            is_deleted: true,
            offers: [makeOffer({ is_deleted: true })]
          })
        ]
      })
    );

    renderEditor();

    expect(await screen.findByText("Default - Offer")).toBeInTheDocument();
    expect(screen.getByText("Offer A")).toBeInTheDocument();
    expect(screen.getByText("Удалён")).toBeInTheDocument();
    expect(screen.getByLabelText("Восстановить предложение")).toBeInTheDocument();
    expect(screen.queryByLabelText("Удалить поток")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Восстановить поток")).not.toBeInTheDocument();
  });

  it("does not render the add-offer form for redirect streams", async () => {
    fetchCampaignDetail.mockResolvedValue(
      makeCampaign({
        streams: [
          makeStream({
            id: 11,
            keitaro_id: 9001,
            name: "GEO - Google",
            type: "regular",
            schema: "redirect",
            offers: []
          })
        ]
      })
    );

    renderEditor();

    expect(await screen.findByText("GEO - Google")).toBeInTheDocument();
    expect(screen.queryByLabelText("Добавить предложение")).not.toBeInTheDocument();
  });

  it("deletes an offer through PATCH", async () => {
    const user = userEvent.setup();
    renderEditor();

    const [deleteButton] = await screen.findAllByLabelText("Удалить предложение");
    await user.click(deleteButton);

    expect(updateOffer).toHaveBeenCalledWith(100, { is_deleted: true }, 3);
  });

  it("restores a deleted offer through PATCH", async () => {
    const user = userEvent.setup();
    fetchCampaignDetail.mockResolvedValue(
      makeCampaign({
        streams: [makeStream({ offers: [makeOffer({ is_deleted: true })] })]
      })
    );

    renderEditor();

    await user.click(await screen.findByLabelText("Восстановить предложение"));

    expect(updateOffer).toHaveBeenCalledWith(100, { is_deleted: false }, 3);
  });

  it("pins an offer with an explicit weight", async () => {
    const user = userEvent.setup();
    renderEditor();

    const [pinButton] = await screen.findAllByLabelText("Закрепить вес");
    await user.click(pinButton);

    expect(await screen.findByText("Закрепить вес предложения")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Закрепить" }));

    expect(updateOffer).toHaveBeenCalledWith(100, { is_pinned: true, pinned_share: 60 }, 3);
  });

  it("rejects an out-of-range pinned weight before calling the API", async () => {
    const user = userEvent.setup();
    renderEditor();

    const [pinButton] = await screen.findAllByLabelText("Закрепить вес");
    await user.click(pinButton);
    const input = await screen.findByLabelText("Вес, %");
    await user.clear(input);
    await user.type(input, "150");
    await user.click(screen.getByRole("button", { name: "Закрепить" }));

    expect(await screen.findByText("Введите целое число от 0 до 100")).toBeInTheDocument();
    expect(updateOffer).not.toHaveBeenCalled();
  });

  it("shows the dirty indicator", async () => {
    fetchCampaignDetail.mockResolvedValue(makeCampaign({ has_local_changes: true }));

    renderEditor();

    expect(await screen.findByText("Есть несинхронизированные изменения")).toBeInTheDocument();
  });

  it("pushes changes and switches to the synchronized indicator", async () => {
    const user = userEvent.setup();
    fetchCampaignDetail.mockResolvedValue(makeCampaign({ has_local_changes: true }));

    renderEditor();

    await user.click(await screen.findByRole("button", { name: "Отправить изменения в Keitaro" }));

    await waitFor(() => {
      expect(pushCampaignChanges).toHaveBeenCalledWith("1", { expectedRevision: 3 });
    });
    expect(await screen.findByText("Синхронизировано с Keitaro")).toBeInTheDocument();
  });

  it("shows a warning for a partial push", async () => {
    const user = userEvent.setup();
    fetchCampaignDetail.mockResolvedValue(makeCampaign({ has_local_changes: true }));
    pushCampaignChanges.mockResolvedValue({
      success: false,
      campaign: makeCampaign({ has_local_changes: true }),
      results: [
        {
          stream_id: 10,
          keitaro_id: 9002,
          status: "error",
          code: "KEITARO_API_ERROR",
          message: "boom"
        }
      ]
    });

    renderEditor();

    await user.click(await screen.findByRole("button", { name: "Отправить изменения в Keitaro" }));

    expect(
      (await screen.findAllByText("Часть потоков не удалось отправить")).length
    ).toBeGreaterThan(0);
    expect(screen.getByText(/KEITARO_API_ERROR/)).toBeInTheDocument();
  });

  it("asks for confirmation before a load that would drop local changes", async () => {
    const user = userEvent.setup();
    fetchCampaignDetail.mockResolvedValue(makeCampaign({ has_local_changes: true }));

    renderEditor();

    await user.click(await screen.findByRole("button", { name: "Загрузить из Keitaro" }));

    expect(await screen.findByText("Потерять несинхронизированные изменения?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Загрузить" }));

    await waitFor(() => {
      expect(loadCampaignStreams).toHaveBeenCalledWith("1", { force: true });
    });
  });

  it("loads from Keitaro without confirmation when there are no local changes", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(await screen.findByRole("button", { name: "Загрузить из Keitaro" }));

    await waitFor(() => {
      expect(loadCampaignStreams).toHaveBeenCalledWith("1", { force: false });
    });
  });

  it("shows warnings returned by a Keitaro load", async () => {
    const user = userEvent.setup();
    loadCampaignStreams.mockResolvedValue(makeCampaign({ warnings: ["Часть данных недоступна"] }));

    renderEditor();
    await user.click(await screen.findByRole("button", { name: "Загрузить из Keitaro" }));

    expect(await screen.findByText("Часть данных недоступна")).toBeInTheDocument();
  });

  it("asks for confirmation when the server reports LOCAL_CHANGES_PENDING", async () => {
    const user = userEvent.setup();
    loadCampaignStreams.mockRejectedValueOnce(
      new ApiError("Есть несинхронизированные изменения", {
        status: 409,
        code: "LOCAL_CHANGES_PENDING"
      })
    );

    renderEditor();

    await user.click(await screen.findByRole("button", { name: "Загрузить из Keitaro" }));
    expect(await screen.findByText("Потерять несинхронизированные изменения?")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Загрузить" }));
    await waitFor(() => {
      expect(loadCampaignStreams).toHaveBeenLastCalledWith("1", { force: true });
    });
  });

  it("reports a revision conflict and clears it after refresh", async () => {
    const user = userEvent.setup();
    fetchCampaignDetail.mockResolvedValue(makeCampaign({ has_local_changes: true }));
    pushCampaignChanges.mockRejectedValue(
      new ApiError("Данные изменились в другой вкладке", {
        status: 409,
        code: "REVISION_CONFLICT"
      })
    );

    renderEditor();

    await user.click(await screen.findByRole("button", { name: "Отправить изменения в Keitaro" }));

    expect(await screen.findByText(/Данные изменились в другой вкладке/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Обновить" }));

    await waitFor(() => {
      expect(screen.queryByText(/Данные изменились в другой вкладке/)).not.toBeInTheDocument();
    });
  });

  it("discards local changes after confirmation", async () => {
    const user = userEvent.setup();
    fetchCampaignDetail.mockResolvedValue(makeCampaign({ has_local_changes: true }));

    renderEditor();

    await user.click(await screen.findByRole("button", { name: "Отменить изменения" }));
    expect(await screen.findByText("Отменить изменения?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отменить изменения" }));

    expect(discardCampaignChanges).toHaveBeenCalledWith("1");
  });

  it("adds an offer from the autocomplete", async () => {
    const user = userEvent.setup();
    renderEditor();

    const [input] = await screen.findAllByLabelText("Добавить предложение");
    await user.type(input, "Offer D");

    const option = await screen.findByText("Offer D (ID: 44)");
    await user.click(option);

    const [addButton] = screen.getAllByRole("button", { name: "Добавить" });
    await user.click(addButton);

    await waitFor(() => {
      expect(addOffer).toHaveBeenCalledWith(10, {
        offer_id: 44,
        name: "Offer D",
        expectedRevision: 3
      });
    });
  });

  it("opens the campaign in Keitaro in a new tab", async () => {
    renderEditor();

    const link = await screen.findByRole("link", { name: /Открыть в Keitaro/ });

    expect(link).toHaveAttribute("href", "https://keitaro.test/admin/#!/campaign/456/main");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("shows 404 for a non-numeric campaign id", async () => {
    renderEditor("not-a-number");

    expect(await screen.findByText("Кампания не найдена")).toBeInTheDocument();
    expect(fetchCampaignDetail).not.toHaveBeenCalled();
  });
});
