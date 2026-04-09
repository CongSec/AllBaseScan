# 前言

一句话总结：通过灵活匹配上下行来实现简单的基线排查

最近在进行安全排查工作时，需要检查大量交换机配置是否合理。面对满屏的命令行界面，不仅看得眼花缭乱，而且对部分配置内容也并非完全熟悉。这类简单的文本处理工作，本想借助在线网站来完成，却迟迟没找到合适的工具，于是便自行编写了一款脚本，通过模糊批量筛选文字的方式，为交换机配置排查提供了便利。

实际上，这款工具的应用范围并不局限于交换机配置排查，在其他文本分析场景中也能发挥作用，比如流量日志分析等。

它的**主要优点**如下：

1. **自定义查询方式**：在关键字查询方面支持多种自定义方式，例如可以输出匹配到的关键字附近的几行内容，或者输出关键字向上、向下的几行内容，也能输出关键字附近的几个字符；并且支持对输出的字符进行文本排除，只要满足其中一个排除条件，就能排查掉该结果。
2. 操作便捷的 **GUI 界面**：直观的图形化界面设计，让操作变得简单易懂，即便是不熟悉命令行的用户也能轻松上手。
3. **灵活的关键字存储**：匹配所需的关键字存储在 config.json 文件中，方便下次直接调用，同时也便于进行**迁移和分类保存**，提升了工作的连续性和高效性。
4. **关键字勾选**功能：支持对关键字进行勾选与取消勾选操作，可根据实际需求灵活选择需要匹配的关键字，增强了使用的灵活性。
5. **多关键字同时匹配**：能够同时对多个关键字进行匹配，一次性满足复杂的筛选需求，减少了重复操作的麻烦。
6. 支持**导出 csv 文件**：便于用户查看内容以及进行进一步的筛选操作，实现了数据的可视化呈现。
7. **批量匹配功能**：既可以对多个文件进行批量匹配，也能直接输入内容进行匹配，满足了不同场景下的使用需求。
8. **自动导出功能：** 无论是单个匹配还是批量处理，输出的结果都会自动保存在当前data目录下
9. **目录递归匹配**：递归匹配文件夹的文件，常用于源码查询，日志查询等
10. **大文本匹配**：经过测试可以匹配大量文本文字，字数可达数亿（数据源:[链接](https://ld246.com/article/1729617471759)）

github链接：[CongSec/SearchTool: 简单正则表达式图形化](https://github.com/CongSec/SearchTool)

# GUI界面

### 关键字添加界面

![image](http://congsec.oss-cn-beijing.aliyuncs.com/congsec/siyuan-assets/image-20250829172312-dpq5u5y.png)

### 单个匹配界面

![image](http://congsec.oss-cn-beijing.aliyuncs.com/congsec/siyuan-assets/network-asset-image-20250826232539-7tpnidr.png "单个匹配界面")

### 批量处理界面

![image](http://congsec.oss-cn-beijing.aliyuncs.com/congsec/siyuan-assets/image-20250919160006-txo4dxi.png)

### 结果导出界面

![image](http://congsec.oss-cn-beijing.aliyuncs.com/congsec/siyuan-assets/network-asset-image-20250826232719-4ish38l.png "结果导出界面")

### 结果自动导出

![image](http://congsec.oss-cn-beijing.aliyuncs.com/congsec/siyuan-assets/image-20250912214122-2m92sjq.png)

### 大文本批量查询（数亿级别）

![image](http://congsec.oss-cn-beijing.aliyuncs.com/congsec/siyuan-assets/image-20250912214202-lbhb232.png)

![image](http://congsec.oss-cn-beijing.aliyuncs.com/congsec/siyuan-assets/image-20250912214202-lbhb232.png)