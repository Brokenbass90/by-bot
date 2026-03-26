// ExportForexM5Batch.mq5
// Exports M5 candles for a CSV pair list into MQL5/Files as MT-style CSV.
#property script_show_inputs

input string InpPairs = "EURUSD,GBPUSD,EURJPY,USDJPY,AUDJPY,USDCAD,GBPJPY";
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M5;
input int InpBars = 120000;
input string InpOutSuffix = "_M5.csv";

string _trim(string s) {
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
}

void _export_pair(const string symbol_raw) {
   string symbol = _trim(symbol_raw);
   StringToUpper(symbol);
   if(symbol == "") return;

   if(!SymbolSelect(symbol, true)) {
      PrintFormat("skip %s: SymbolSelect failed", symbol);
      return;
   }

   MqlRates rates[];
   int got = CopyRates(symbol, InpTimeframe, 0, InpBars, rates);
   if(got <= 0) {
      PrintFormat("skip %s: CopyRates failed (got=%d err=%d)", symbol, got, GetLastError());
      return;
   }
   ArraySetAsSeries(rates, true);

   string file_name = symbol + InpOutSuffix;
   int fh = FileOpen(file_name, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(fh == INVALID_HANDLE) {
      PrintFormat("skip %s: FileOpen failed (%s) err=%d", symbol, file_name, GetLastError());
      return;
   }

   // Keep MT-like headers so project importer can parse date/time + OHLCV.
   FileWrite(fh, "<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>", "<TICKVOL>");

   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(digits < 0 || digits > 10) digits = 5;

   // Write oldest -> newest.
   for(int i = got - 1; i >= 0; --i) {
      string d = TimeToString(rates[i].time, TIME_DATE);
      string t = TimeToString(rates[i].time, TIME_SECONDS);
      FileWrite(
         fh,
         d,
         t,
         DoubleToString(rates[i].open, digits),
         DoubleToString(rates[i].high, digits),
         DoubleToString(rates[i].low, digits),
         DoubleToString(rates[i].close, digits),
         IntegerToString((int)rates[i].tick_volume)
      );
   }

   FileClose(fh);
   PrintFormat("exported %s rows=%d file=%s", symbol, got, file_name);
}

void OnStart() {
   Print("ExportForexM5Batch start");
   PrintFormat("terminal_data_path=%s", TerminalInfoString(TERMINAL_DATA_PATH));
   PrintFormat("expected_output_dir=%s\\MQL5\\Files", TerminalInfoString(TERMINAL_DATA_PATH));

   string parts[];
   int n = StringSplit(InpPairs, ',', parts);
   if(n <= 0) {
      Print("No pairs in InpPairs");
      return;
   }

   for(int i = 0; i < n; ++i) {
      _export_pair(parts[i]);
   }

   Print("ExportForexM5Batch done");
}
