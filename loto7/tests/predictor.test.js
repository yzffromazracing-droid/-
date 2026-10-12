const test = require("node:test");
const assert = require("node:assert/strict");
const Loto7 = require("../predictor.js");

function fakeDraws(n, seed = 42) {
  const rng = Loto7.seededRandom(seed);
  const draws = [];
  for (let i = 1; i <= n; i++) {
    const pool = Array.from({ length: 37 }, (_, k) => k + 1);
    const nums = [];
    while (nums.length < 9) nums.push(pool.splice(Math.floor(rng() * pool.length), 1)[0]);
    draws.push({ no: i, main: nums.slice(0, 7).sort((a, b) => a - b), bonus: nums.slice(7) });
  }
  return draws;
}

test("CSV（回号・日付・本数字・ボーナス）を解析できる", () => {
  const text = [
    "回号,日付,本数字1,本数字2,本数字3,本数字4,本数字5,本数字6,本数字7,B1,B2",
    "2,2013/04/12,3,8,15,19,23,30,37,1,2",
    "1,2013/04/05,1,5,9,12,20,28,33,7,36",
  ].join("\n");
  const draws = Loto7.parseResults(text);
  assert.equal(draws.length, 2);
  assert.deepEqual(draws[0], { no: 1, main: [1, 5, 9, 12, 20, 28, 33], bonus: [7, 36] });
  assert.equal(draws[1].no, 2);
});

test("「第N回」形式や金額付きのコピペにも対応する", () => {
  const text = "第600回\t2024年10月11日\t02 07 11 18 25 31 35\t(04)(22)\t1等 2口 600,000,000円";
  const [d] = Loto7.parseResults(text);
  assert.equal(d.no, 600);
  assert.deepEqual(d.main, [2, 7, 11, 18, 25, 31, 35]);
  assert.deepEqual(d.bonus, [4, 22]);
});

test("本数字だけの行も読み込み、範囲外や重複は無視する", () => {
  const text = "1 2 3 4 5 6 7\n1 1 2 3 4 5 6\n1 2 3 4 5 6 38\n";
  const draws = Loto7.parseResults(text);
  assert.equal(draws.length, 1);
  assert.deepEqual(draws[0].bonus, []);
});

test("同じ回号の重複行は1回分として扱う", () => {
  const line = "10,4,8,15,16,23,30,37,1,2";
  assert.equal(Loto7.parseResults(line + "\n" + line).length, 1);
});

test("統計: 出現回数とご無沙汰回数", () => {
  const draws = [
    { no: 1, main: [1, 2, 3, 4, 5, 6, 7], bonus: [] },
    { no: 2, main: [1, 8, 9, 10, 11, 12, 13], bonus: [] },
  ];
  const s = Loto7.computeStats(draws, 1);
  const n1 = s.numbers[0];
  assert.equal(n1.total, 2);
  assert.equal(n1.recent, 1);
  assert.equal(n1.gap, 0);
  assert.equal(s.numbers[1].gap, 1); // 2 は1回前に出た
  assert.equal(s.numbers[36].gap, 2); // 37 は一度も出ていない
});

test("予想: 1〜37の重複しない7個を指定数だけ生成する", () => {
  const draws = fakeDraws(100);
  for (const strategy of ["hot", "cold", "mixed", "random"]) {
    const sets = Loto7.predict(draws, { strategy, count: 10, rng: Loto7.seededRandom(7) });
    assert.equal(sets.length, 10);
    assert.equal(new Set(sets.map((s) => s.join())).size, 10);
    for (const s of sets) {
      assert.equal(new Set(s).size, 7);
      assert.ok(s.every((n) => n >= 1 && n <= 37));
      assert.deepEqual(s, s.slice().sort((a, b) => a - b));
      assert.ok(Loto7.isBalanced(s, Loto7.computeStats(draws)));
    }
  }
});

test("予想: データが空でも生成できる", () => {
  const sets = Loto7.predict([], { count: 3, rng: Loto7.seededRandom(1) });
  assert.equal(sets.length, 3);
});

test("バックテスト: 無作為な抽選では平均一致数がランダム期待値付近になる", () => {
  const draws = fakeDraws(300);
  const r = Loto7.backtest(draws, { strategy: "hot", tickets: 5, minHistory: 50 });
  assert.equal(r.tickets, 250 * 5);
  assert.ok(Math.abs(r.averageHits - r.expectedRandom) < 0.15, `avg=${r.averageHits}`);
});
