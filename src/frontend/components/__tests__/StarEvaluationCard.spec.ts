// src/frontend/components/__tests__/StarEvaluationCard.spec.ts

// VitestとVue Test Utilsから必要なものをインポート！
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import StarEvaluationCard from '@/components/StarEvaluationCard.vue';

// API仕様書から持ってきたモックデータ！これでテストするよん
const mockEvaluation = {
  situation: { score: 8.5, feedback: "状況説明が具体的" },
  task: { score: 7.0, feedback: "課題の明確化が必要" },
  action: { score: 9.0, feedback: "行動が詳細で良い" },
  result: { score: 6.4, feedback: "結果が弱いかも..." } // 赤色になるケースもテスト！
};

// 'StarEvaluationCard.vue' のテストスイートを開始！
describe('StarEvaluationCard.vue', () => {
  // ①評価データがない（nullの）時、ちゃんとメッセージ出てる？
  it('evaluation propがnullの場合、フォールバックメッセージを表示する', () => {
    const wrapper = mount(StarEvaluationCard, {
      props: { evaluation: null }
    });
    // せんぱいが設定したメッセージに合わせて、ここを修正！📝
    expect(wrapper.text()).toContain('評価データがまだありません'); // ◀️ 「まだ」を追加！
  });

  // ②評価データを渡した時、内容がぜんぶ表示されてる？
  it('evaluation propを受け取った時、STARのフィードバックを正しく表示する', () => {
    const wrapper = mount(StarEvaluationCard, {
      props: { evaluation: mockEvaluation }
    });

    // 各フィードバックが表示されてるかチェック！
    expect(wrapper.text()).toContain('状況説明が具体的');
    expect(wrapper.text()).toContain('課題の明確化が必要');
    expect(wrapper.text()).toContain('行動が詳細で良い');
    expect(wrapper.text()).toContain('結果が弱いかも...');
  });

  // ③スコアに応じた色分け、ちゃんとできてる？ここ超重要！
  it('スコアに応じて正しいCSSクラスを適用する', () => {
    const wrapper = mount(StarEvaluationCard, {
      props: { evaluation: mockEvaluation }
    });

    // 評価項目を全部見つけて、一個ずつクラスをチェック！
    const scoreBadges = wrapper.findAll('[data-testid="score-badge"]');

    // Situation (8.5点) は緑色のはず！💚
    expect(scoreBadges[0].classes()).toContain('bg-green-100');

    // Task (7.0点) は黄色のはず！💛
    expect(scoreBadges[1].classes()).toContain('bg-yellow-100');

    // Action (9.0点) は緑色！💚
    expect(scoreBadges[2].classes()).toContain('bg-green-100');

    // Result (6.4点) は赤色だよね！❤️
    expect(scoreBadges[3].classes()).toContain('bg-red-100');
  });
}); 