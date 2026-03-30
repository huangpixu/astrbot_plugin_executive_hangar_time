import asyncio
from pathlib import Path
from rsi_scraper import fetch_org_members
from text_to_img import members_to_image

async def test_run():
    print("正在获取鹿港成员信息，请稍候...")
    members = await fetch_org_members("GFHB")
    
    if not members:
        print("❌ 获取成员信息失败！")
        return

    print(f"✅ 成功获取 {len(members)} 名成员信息！")
    print("前 5 名成员示例：")
    for m in members[:5]:
        print(f"  - {m['handle']} ({m['moniker']}) - {m['rank']} (颜色级别: {m['color_level']})")
        
    save_dir = Path("./")
    print("\n正在生成图片...")
    img_path = members_to_image(members, save_dir)
    
    print(f"✅ 图片生成成功，保存在: {img_path}")
    print("你可以直接在 IDE 中打开该图片查看效果！")

if __name__ == "__main__":
    asyncio.run(test_run())