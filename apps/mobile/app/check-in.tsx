import { useState } from "react";
import { Button, Text, View } from "react-native";
import { checkIn } from "../src/services/api";

export default function CheckIn() {
  const [status, setStatus] = useState<string>("idle");
  const [busy, setBusy] = useState(false);

  async function onPress(account_id: string) {
    if (busy) return; // evita doble tap -> no duplica operacion
    setBusy(true);
    setStatus("sending");
    try {
      await checkIn(account_id);
      setStatus("confirmed"); // solo confirmar si el server responde 2xx
    } catch {
      setStatus("error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View>
      <Text>Selecciona cuenta</Text>
      <Button title="Entrada Medical" onPress={() => onPress("medical")} />
      <Button title="Entrada Medical 2" onPress={() => onPress("medical-2")} />
      <Text testID="checkin-status">{status}</Text>
    </View>
  );
}
