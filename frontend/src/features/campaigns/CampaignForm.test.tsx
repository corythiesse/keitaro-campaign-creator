import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as offersApi from "../../shared/api/offers";
import { CampaignForm } from "./CampaignForm";

vi.mock("../../shared/api/offers", () => ({
  searchOffers: vi.fn()
}));

const searchOffers = vi.mocked(offersApi.searchOffers);

function renderForm(overrides: Partial<Parameters<typeof CampaignForm>[0]> = {}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const onCancel = vi.fn();
  render(
    <CampaignForm submitting={false} onSubmit={onSubmit} onCancel={onCancel} {...overrides} />
  );
  return { onSubmit, onCancel };
}

beforeEach(() => {
  searchOffers.mockResolvedValue([{ id: 44, name: "Offer D" }]);
});

describe("CampaignForm", () => {
  it("shows validation errors and does not submit empty values", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();

    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(await screen.findByText("Введите название кампании")).toBeInTheDocument();
    expect(screen.getByText("Укажите хотя бы одну страну")).toBeInTheDocument();
    expect(screen.getByText("Выберите оффер из списка")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("rejects invalid and duplicate ISO codes", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText("Код страны"), "MX, MEX");
    await user.click(screen.getByRole("button", { name: "Создать" }));
    expect(
      await screen.findByText("Используйте ISO-коды через запятую, например MX, AU, RO")
    ).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Код страны"));
    await user.type(screen.getByLabelText("Код страны"), "MX, MX");
    await user.click(screen.getByRole("button", { name: "Создать" }));
    expect(await screen.findByText("Удалите повторяющиеся GEO-коды")).toBeInTheDocument();
  });

  it("submits trimmed values with the selected offer id", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();

    await user.type(screen.getByLabelText("Название"), "  Test campaign  ");
    await user.type(screen.getByLabelText("Код страны"), " MX, AU ");
    await user.type(screen.getByLabelText("Предложения"), "Offer");

    const option = await screen.findByText("Offer D (ID: 44)");
    await user.click(option);
    expect(screen.getByLabelText("Предложения")).toHaveValue("Offer D (ID: 44)");
    await user.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        name: "Test campaign",
        geo: "MX, AU",
        offer_id: 44
      });
    });
  });

  it("disables actions while submitting", () => {
    renderForm({ submitting: true });

    expect(screen.getByRole("button", { name: "Отмена" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Создать" })).toBeDisabled();
  });
});
