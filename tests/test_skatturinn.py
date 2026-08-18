import asyncio

from scripts import skatturinn


def test_chain_omits_unavailable_owner_kennitala(monkeypatch):
    async def fake_get_company_info(kennitala):
        return skatturinn.Company(
            kennitala=kennitala,
            name="Example ehf.",
            beneficial_owners=[
                skatturinn.Owner(
                    name="Owner Without KT",
                    birth_year_month="1980-JANÚAR",
                ),
                skatturinn.Owner(
                    name="Owner With KT",
                    kennitala="010180-1234",
                ),
            ],
        )

    monkeypatch.setattr(skatturinn, "get_company_info", fake_get_company_info)

    chain = asyncio.run(skatturinn.map_ownership_chain("5012043070"))

    assert "kennitala" not in chain["owners"][0]
    assert chain["owners"][0]["birth_year_month"] == "1980-JANÚAR"
    assert chain["owners"][1]["kennitala"] == "0101801234"
