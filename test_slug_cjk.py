"""中文為主的條目 slug：不該塌成 insight-note / untitled，要挖出內文的 ASCII 技術詞。"""
import fxauto as F

TITLE = '派給沙箱外執行人的工單禁止段要以不變量表述'


def test():
    # ROOT 能抽出成串技術詞 → 走上游的 _slug_source
    src = 'deep 在 git rm -r --cached . 被擋後自行加 -f'
    assert F._slug_pick(None, src, TITLE, fallback='insight')[0] == 'deep-git-rm-r-cached'

    # ROOT 是中文敘述、ascii 只是零星專有名詞 → title-weak，title 又全中文塌成空，
    # 這時退回從 ROOT 挖技術詞，而不是通用 fallback（舊行為產出 insight-note，
    # 工具自己標記為路由黑洞）。
    weak = '執行人遇阻會找最接近的變體，禁令列舉指令名只會被繞過，例如 git checkout 完全不觸犯禁令'
    slug, kind = F._slug_pick(None, weak, TITLE, fallback='insight')
    assert kind == 'title-weak' and slug == 'git-checkout', (slug, kind)

    # 完全沒有 ASCII 可挖 → 維持既有 fallback（補 -note 避開路由黑洞）
    assert F.slugify('全中文標題', fallback='insight', extra='內文也全中文') == 'insight-note'

    # 標題本來就有 ASCII → 行為不變
    assert F.slugify('deep-run 被 teardown') == 'deep-run-teardown'

    # symptoms 是 list，_slug_extra 要能攤平
    assert F._slug_extra(['git checkout .'], 'launchctl bootout') == 'git checkout . launchctl bootout'
    print('OK')


if __name__ == '__main__':
    test()
