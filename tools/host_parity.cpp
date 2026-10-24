// Host-side parity harness: runs the exported C++ model on data/test.csv and prints one prediction per row.
// Built by tools/s1_3_export.py with -DMODEL_HEADER="..." -DMODEL_CLASS=...
#include <cstdio>
#include MODEL_HEADER
int main(int argc, char **argv) {
  FILE *f = fopen(argv[1], "r");
  if (!f) return 1;
  char line[256];
  if (!fgets(line, sizeof line, f)) return 1;  // header
  MODEL_CLASS clf;
  while (fgets(line, sizeof line, f)) {
    float x[4], y;
    if (sscanf(line, "%f,%f,%f,%f,%f", &x[0], &x[1], &x[2], &x[3], &y) == 5) printf("%.6f\n", clf.predict(x));
  }
  fclose(f);
  return 0;
}
