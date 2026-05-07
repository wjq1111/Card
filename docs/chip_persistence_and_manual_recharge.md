# Chip Persistence And Manual Recharge

## Current Behavior

- Player chip balances are stored on the server in `runtime_logs/player_chips.json`.
- The current lightweight identity key is the login name, so `Alice` and `alice` map to the same balance.
- A new player starts with `2000` chips the first time that name logs in.
- Chip balances are synced back to the file after each completed hand and when a player stands up.

## Manual Recharge Flow

This is the simplest practical flow when you use a personal QR code for payment:

1. The player scans your WeChat or Alipay QR code and pays you.
2. You manually verify the payment in your payment app.
3. You add chips on the server with:

```powershell
python tools\recharge_player.py --name Alice --amount 5000
```

4. The player's stored balance is updated in `runtime_logs/player_chips.json`.
5. The next time that player sits down, the room uses the updated balance.

## Notes

- This flow is manual and is suitable for internal testing or a very small private game.
- Because the project does not yet have a real account system, login names should be treated as unique.
- For production automation, replace name-based identity with a real account id and add paid-order records plus callback verification.
