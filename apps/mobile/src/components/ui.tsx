import { PropsWithChildren } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, TextInputProps, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Svg, { Path } from 'react-native-svg';
import { theme } from '../theme';
const c = theme.colors;
export function Screen({ children }: PropsWithChildren) {
 return <SafeAreaView style={s.screen}><KeyboardAvoidingView style={s.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={s.scroll}><View style={s.content}>{children}</View></ScrollView></KeyboardAvoidingView></SafeAreaView>;
}
export function Brand() {
 return <View style={s.brand}><View style={s.logo}><Svg width={36} height={36} viewBox="0 0 24 24"><Path d="M2 12h5l3-9 4 18 3-9h5" fill="none" stroke="white" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" /></Svg></View><Text accessibilityRole="header" style={s.title}>LivePulse</Text><Text style={s.subtitle}>Gestiona tus transmisiones en vivo</Text></View>;
}
export function Card({ children }: PropsWithChildren) { return <View style={s.card}>{children}</View>; }
export function Footer() { return <Text style={s.footer}>LivePulse · Gestión de transmisiones</Text>; }
export function Button({ title, onPress, busy = false }: { title: string; onPress: () => void; busy?: boolean }) {
 return <Pressable accessibilityRole="button" accessibilityState={{ disabled: busy, busy }} disabled={busy} onPress={onPress} style={({ pressed }) => [s.button, (pressed || busy) && { opacity: 0.65 }]}>{busy ? <ActivityIndicator color="white" /> : <Text style={s.buttonText}>{title}</Text>}</Pressable>;
}
export function Field({ label, ...props }: TextInputProps & { label: string }) {
 return <View style={s.field}><Text style={s.label}>{label}</Text><TextInput accessibilityLabel={label} placeholderTextColor="#94a3b8" {...props} style={[s.input, props.style]} /></View>;
}
export function ErrorText({ message }: { message: string }) { return message ? <Text accessibilityRole="alert" style={s.error}>{message}</Text> : null; }
export const s = StyleSheet.create({
 screen: { flex: 1, backgroundColor: c.background }, scroll: { flexGrow: 1, padding: 20 },
 content: { width: '100%', maxWidth: 430, alignSelf: 'center', flexGrow: 1 },
 brand: { alignItems: 'center', marginTop: 12, marginBottom: 30 },
 logo: { width: 64, height: 64, borderRadius: 24, backgroundColor: c.primary, alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
 title: { color: c.ink, fontSize: 30, fontWeight: '700', marginBottom: 6 },
 subtitle: { color: c.muted, fontSize: 14, lineHeight: 21 },
 card: { backgroundColor: c.card, borderWidth: 1, borderColor: c.border, borderRadius: 28, padding: 22, marginBottom: 16, shadowColor: c.ink, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.05, shadowRadius: 18, elevation: 2 },
 heading: { color: c.ink, fontSize: 21, fontWeight: '600', marginBottom: 6 },
 field: { marginTop: 18 }, label: { color: c.ink, fontSize: 14, fontWeight: '500', marginBottom: 8 },
 input: { borderWidth: 1, borderColor: c.border, borderRadius: 24, minHeight: 54, paddingHorizontal: 17, color: c.ink, fontSize: 16, backgroundColor: c.card },
 button: { minHeight: 52, borderRadius: 25, backgroundColor: c.primary, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 16, marginTop: 18 },
 buttonText: { color: 'white', fontSize: 14, fontWeight: '700', textAlign: 'center' },
 link: { color: c.primary, fontSize: 14, fontWeight: '600', paddingVertical: 10 },
 row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' },
 footer: { color: c.muted, textAlign: 'center', fontSize: 12, paddingTop: 30, paddingBottom: 12, marginTop: 'auto' },
 error: { color: c.danger, fontSize: 14, lineHeight: 20, marginTop: 12 },
 notice: { color: '#13618c', backgroundColor: c.pale, borderRadius: 14, padding: 12, fontSize: 12, lineHeight: 18, marginBottom: 18 },
});
