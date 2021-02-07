from pathlib import Path
import yaml
import click

from brownie import Token, Vault, Registry, accounts, network, web3
from eth_utils import is_checksum_address
from semantic_version import Version


DEFAULT_VAULT_NAME = lambda token: f"{token.symbol()} yVault"
DEFAULT_VAULT_SYMBOL = lambda token: f"yv{token.symbol()}"

PACKAGE_VERSION = yaml.safe_load(
    (Path(__file__).parent.parent / "ethpm-config.yaml").read_text()
)["version"]


def get_address(msg: str, default: str = None) -> str:
    val = click.prompt(msg, default=default)

    # Keep asking user for click.prompt until it passes
    while True:

        if is_checksum_address(val):
            return val
        elif addr := web3.ens.address(val):
            click.echo(f"Found ENS '{val}' [{addr}]")
            return addr

        click.echo(
            f"I'm sorry, but '{val}' is not a checksummed address or valid ENS record"
        )
        # NOTE: Only display default once
        val = click.prompt(msg)


def main():
    click.echo(f"You are using the '{network.show_active()}' network")
    dev = accounts.load(click.prompt("Account", type=click.Choice(accounts.load())))
    click.echo(f"You are using: 'dev' [{dev.address}]")

    registry = Registry.at(
        get_address("Vault Registry", default="v2.registry.ychad.eth")
    )

    latest_release = Version("0.0.0")  # Version(registry.latestRelease())
    use_proxy = False  # NOTE: Use a proxy to save on gas for experimental Vaults
    if Version(PACKAGE_VERSION) < latest_release:
        click.echo("Cannot deploy Vault for old API version")
        return
    elif Version(PACKAGE_VERSION) > latest_release:
        if not click.confirm(f"Deploy {PACKAGE_VERSION} as new release"):
            return
    else:
        if not click.confirm("Deploy Experimental Vault"):
            return
        use_proxy = True
    publish_source = click.confirm("Verify source on etherscan?")

    token = Token.at(get_address("ERC20 Token"))

    if use_proxy:
        gov_default = dev.address
    else:
        gov_default = "ychad.eth"
    gov = get_address("Yearn Governance", default=gov_default)

    rewards = get_address(
        "Rewards contract", default="0x93A62dA5a14C80f265DAbC077fCEE437B1a0Efde"
    )
    guardian = get_address("Vault Guardian", default=dev.address)
    name = click.prompt(f"Set description", default=DEFAULT_VAULT_NAME(token))
    symbol = click.prompt(f"Set symbol", default=DEFAULT_VAULT_SYMBOL(token))

    click.echo(
        f"""
    Vault Parameters

   version: {PACKAGE_VERSION}
     token: {token.address}
  governer: {gov}
   rewards: {rewards}
  guardian: {guardian}
      name: '{name}'
    symbol: '{symbol}'
    """
    )

    if click.confirm("Deploy New Vault"):
        args = [
            token,
            gov,
            rewards,
            # NOTE: Empty string `""` means no override (don't use click default tho)
            name if name != DEFAULT_VAULT_NAME(token) else "",
            symbol if symbol != DEFAULT_VAULT_SYMBOL(token) else "",
        ]
        if use_proxy:
            # NOTE: Must always include guardian, even if default
            args.insert(2, guardian)
            txn_receipt = registry.newExperimentalVault(*args, {"from": dev})
            vault = Vault.at(txn_receipt.events["NewExperimentalVault"]["vault"])
            if publish_source:
                Vault.publish_source(vault)
            click.echo(f"Experimental Vault deployed [{vault.address}]")
            click.echo("    NOTE: Vault is not registered in Registry!")
        else:
            if guardian != dev.address:
                # NOTE: Only need to include if guardian is not self
                args.append(guardian)
            vault = dev.deploy(Vault, publish_source=publish_source)
            vault.initialize(*args)
            click.echo(f"New Vault Release deployed [{vault.address}]")
            click.echo(
                "    NOTE: Vault is not registered in Registry, please register!"
            )
