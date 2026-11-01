import {
  createConnector as createConnectorRequest,
  deleteConnector as deleteConnectorRequest,
  listConnectors,
  updateConnector as updateConnectorRequest,
} from "../runtime/connector-api.js";
import { renderConnectorSelect } from "../components/connector-select.js";

export function createConnectorController({
  getSelectedId,
  setSelectedId,
  setChoices,
  getSelect,
  buildPayload,
  applyConnector,
  clearConnectorFields,
  savePreference,
  refreshComposer,
}) {
  async function load(selected = getSelectedId()) {
    const { connectors } = await listConnectors();
    setChoices(connectors);
    const selectedId = connectors.find((item) => item.id === selected)?.id || connectors[0]?.id || "";
    setSelectedId(selectedId);
    renderConnectorSelect(getSelect(), connectors, selectedId);
    const connector = connectors.find((item) => item.id === selectedId);
    if (connector) applyConnector(connector);
    else clearConnectorFields();
    refreshComposer();
    return { connectors, selectedId, connector };
  }

  async function create(name) {
    const connector = await createConnectorRequest(buildPayload(name));
    await load(connector.id);
    await savePreference(connector.id);
    return connector;
  }

  async function save() {
    const id = getSelectedId();
    if (!id) return null;
    const name = getSelect().selectedOptions[0]?.text || "当前连接";
    await updateConnectorRequest(id, buildPayload(name));
    await load(id);
    await savePreference(id);
    return id;
  }

  async function remove() {
    const id = getSelectedId();
    if (!id) return;
    await deleteConnectorRequest(id);
    setSelectedId("");
    await savePreference("");
    await load();
  }

  return { load, create, save, remove };
}
