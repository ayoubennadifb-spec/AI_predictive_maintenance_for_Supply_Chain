import { app } from "./app";
import { config } from "./config";

app.listen(config.port, () => {
  // eslint-disable-next-line no-console
  console.log(`RBAC auth server listening on port ${config.port}`);
});


