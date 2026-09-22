import { Link } from "expo-router";
import { Text, View } from "react-native";

export default function Index() {
  return (
    <View>
      <Text>LivePulse</Text>
      <Link href="/check-in">Marcar entrada</Link>
    </View>
  );
}
