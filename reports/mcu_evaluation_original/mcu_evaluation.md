# MCU RAG Evaluation Report

Generated: 2026-09-08T16:12:23.801816+00:00
Questions: 12
Elapsed: 107.9s

## Summary

| Metric | Mean | Median | Min | Max |
|--------|------|--------|-----|-----|
| NDCG@10 | 0.9311 | 1.0000 | 0.3562 | 1.0000 |
| Recall@10 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

Answer verdicts: {'correct': 3, 'partial': 4, 'incorrect': 5, 'abstained': 0}
Improved from no-context: 0/12

---

## mcu-draft-001

**Question:** On an STM32F103C8, USART1 is clocked and PA12 is configured as an alternate-function output for USART1 RTS, but PA12 stays high. CAN is unused and its clock is disabled. What could cause this, and how can I fix it?

**Gold pages:** [{'doc_id': 'st_stm32f103_errata_es096', 'page_number': 10, 'section': '2.3.1', 'grade': 2, 'support': 'Complete CAN/USART1_RTS conflict conditions and unused-CAN remapping workaround.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 60010 | st_stm32f103_errata_es096 | 10 | 44.2812 |
| 2 | 60013 | st_stm32f103_errata_es096 | 13 | 43.0625 |
| 3 | 60011 | st_stm32f103_errata_es096 | 11 | 42.7500 |
| 4 | 60012 | st_stm32f103_errata_es096 | 12 | 41.4688 |
| 5 | 60022 | st_stm32f103_errata_es096 | 22 | 40.2812 |
| 6 | 60021 | st_stm32f103_errata_es096 | 21 | 40.0938 |
| 7 | 90026 | st_stm32f407_errata_es0182 | 26 | 39.9062 |
| 8 | 60028 | st_stm32f103_errata_es096 | 28 | 39.8750 |
| 9 | 90024 | st_stm32f407_errata_es0182 | 24 | 39.8750 |
| 10 | 50019 | st_stm32f103_datasheet_ds5319 | 19 | 39.5938 |

NDCG@10: 1.0 | Recall@10: 1.0

Retrieval time: 39184.3 ms

### Answer

**[Page 1] The issue might be due to the fact that when CAN is not clocked, the signal on PA12 remains high by default if configured as an alternate function output for USART1 RTS.

[Page 3] To fix this, remap the CAN to another IO configuration through the CAN_REMAP bits of the AFIO_MAPR register when using USART1 RTS.**

Cited pages: [60010, 60011]
Latency: 25323 ms

### Assessment

**Verdict:** incorrect

Core facts met: 0/2

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| Identifies the CAN/USART1_RTS conflict on PA12. | partially_met | ['pa12'] | 0.33 |
| Specifies selecting the unused CAN remap when CAN is unused. | partially_met | ['remap', 'when'] | 0.4 |

---

## mcu-draft-002

**Question:** On an STM32F103x8/xB, TIM3 channel 2 on PB5 stays high with TIM3 and I2C1 both clocked and PB5 configured as an alternate-function output. SMBus Alert is unused. Why does this happen, and what use of CH2 does the errata permit in this configuration?

**Gold pages:** [{'doc_id': 'st_stm32f103_errata_es096', 'page_number': 12, 'section': '2.3.8', 'grade': 2, 'support': 'Complete clock/pin conditions, I2C1_SMBA conflict, high output and input-only workaround.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 60012 | st_stm32f103_errata_es096 | 12 | 54.7188 |
| 2 | 60013 | st_stm32f103_errata_es096 | 13 | 47.1562 |
| 3 | 90022 | st_stm32f407_errata_es0182 | 22 | 45.6250 |
| 4 | 50032 | st_stm32f103_datasheet_ds5319 | 32 | 45.5625 |
| 5 | 50011 | st_stm32f103_datasheet_ds5319 | 11 | 44.8750 |
| 6 | 70178 | st_stm32f103_refman_rm0008 | 178 | 44.5625 |
| 7 | 50033 | st_stm32f103_datasheet_ds5319 | 33 | 44.3750 |
| 8 | 50012 | st_stm32f103_datasheet_ds5319 | 12 | 44.1250 |
| 9 | 100839 | st_stm32f407_refman_rm0090 | 839 | 44.0938 |
| 10 | 90011 | st_stm32f407_errata_es0182 | 11 | 43.6250 |

NDCG@10: 1.0 | Recall@10: 1.0

Retrieval time: 445.1 ms

### Answer

**[Page 1] When TIM3 and I2C1 are both clocked and PB5 is configured as an alternate function output, there is a conflict between the TIM3_CH2 signal and the I2C1 SMBA signal. [Page 1] To avoid this conflict, TIM3_CH2 can only be used in input mode.**

Cited pages: [60012]
Latency: 3295 ms

### Assessment

**Verdict:** partial

Core facts met: 1/2

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| Explains the I2C1_SMBA conflict despite unused alert. | partially_met | ['conflict'] | 0.2 |
| Restricts CH2 to input in the stated configuration. | met | ['ch2', 'input'] | 0.5 |

---

## mcu-draft-003

**Question:** On an STM32F103x8/xB, after updating the independent watchdog settings and immediately entering Stop mode, the next watchdog update hangs and eventually resets the MCU. How can this be prevented?

**Gold pages:** [{'doc_id': 'st_stm32f103_errata_es096', 'page_number': 17, 'section': '2.7.3', 'grade': 2, 'support': 'Failure mechanism and before-Stop workaround.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 60008 | st_stm32f103_errata_es096 | 8 | 33.9062 |
| 2 | 60007 | st_stm32f103_errata_es096 | 7 | 33.5000 |
| 3 | 50018 | st_stm32f103_datasheet_ds5319 | 18 | 33.1875 |
| 4 | 90009 | st_stm32f407_errata_es0182 | 9 | 33.0000 |
| 5 | 60023 | st_stm32f103_errata_es096 | 23 | 32.4688 |
| 6 | 60017 | st_stm32f103_errata_es096 | 17 | 32.2812 |
| 7 | 80035 | st_stm32f407_datasheet_ds8626 | 35 | 32.1875 |
| 8 | 90019 | st_stm32f407_errata_es0182 | 19 | 32.0938 |
| 9 | 100704 | st_stm32f407_refman_rm0090 | 704 | 32.0938 |
| 10 | 90010 | st_stm32f407_errata_es0182 | 10 | 31.6250 |

NDCG@10: 0.3562 | Recall@10: 1.0

Retrieval time: 299.1 ms

### Answer

**To prevent this, ensure that the independent watchdog counter is frozen in debug mode before entering Stop mode. This can be achieved by setting the appropriate bits in the option bytes or through software configuration, as mentioned on Page 3 of the STM32F103x8/xB datasheet.**

Cited pages: [50018]
Latency: 2738 ms

### Assessment

**Verdict:** incorrect

Core facts met: 0/2

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| Waits for RVU and PVU to clear before Stop. | partially_met | ['stop'] | 0.2 |
| Explains that entering Stop before the watchdog update completes can leave the f | partially_met | ['entering', 'stop', 'watchdog', 'set'] | 0.36 |

---

## mcu-draft-004

**Question:** On an STM32F103x8/xB, can clearing a DMA channel's global interrupt flag while the channel is active cause a transfer error to be missed or prevent automatic channel disable? How should software avoid this?

**Gold pages:** [{'doc_id': 'st_stm32f103_errata_es096', 'page_number': 13, 'section': '2.4.1', 'grade': 2, 'support': 'Complete conditions, effects and flag-clearing workaround.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 60013 | st_stm32f103_errata_es096 | 13 | 38.7188 |
| 2 | 90016 | st_stm32f407_errata_es0182 | 16 | 34.6250 |
| 3 | 90030 | st_stm32f407_errata_es0182 | 30 | 34.5938 |
| 4 | 90017 | st_stm32f407_errata_es0182 | 17 | 34.2812 |
| 5 | 70280 | st_stm32f103_refman_rm0008 | 280 | 33.7500 |
| 6 | 60003 | st_stm32f103_errata_es096 | 3 | 33.5625 |
| 7 | 70284 | st_stm32f103_refman_rm0008 | 284 | 33.3438 |
| 8 | 70287 | st_stm32f103_refman_rm0008 | 287 | 32.9688 |
| 9 | 100326 | st_stm32f407_refman_rm0090 | 326 | 32.9375 |
| 10 | 90029 | st_stm32f407_errata_es0182 | 29 | 32.5000 |

NDCG@10: 1.0 | Recall@10: 1.0

Retrieval time: 167.2 ms

### Answer

**On an STM32F103x8/xB, clearing a DMA channel's global interrupt flag while the channel is active can cause a transfer error to be missed or prevent automatic channel disable. To avoid this, software should not clear GIFx flags when the channel is active. Instead, use HTIFx, TCIFx, and TEIFx specific event flags and their corresponding clear bits [Page 1].**

Cited pages: [60013]
Latency: 2377 ms

### Assessment

**Verdict:** correct

Core facts met: 3/3

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| States that both automatic disable and TEIFx reporting can fail. | met | ['automatic', 'disable', 'teifx'] | 0.6 |
| Identifies clearing GIFx in the same clock cycle as a transfer error as the trig | met | ['clearing', 'gifx', 'transfer', 'error'] | 0.57 |
| Uses specific event flags and clear bits instead of clearing active-channel GIFx | met | ['specific', 'event', 'flags', 'clear', 'bits', 'instead', 'clearing', 'gifx'] | 0.89 |

---

## mcu-draft-005

**Question:** On an STM32F407 with PH10 available in the package, EXTI10 is mapped to PH10 while EXTI2 remains mapped to PA2, but the interrupts do not work correctly. Is this pin combination supported?

**Gold pages:** [{'doc_id': 'st_stm32f407_errata_es0182', 'page_number': 11, 'section': '2.2.10', 'grade': 2, 'support': 'Coupled PH10/PH2 routing limitation.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 90011 | st_stm32f407_errata_es0182 | 11 | 39.3438 |
| 2 | 100299 | st_stm32f407_refman_rm0090 | 299 | 34.2812 |
| 3 | 100294 | st_stm32f407_refman_rm0090 | 294 | 34.0625 |
| 4 | 80043 | st_stm32f407_datasheet_ds8626 | 43 | 34.0000 |
| 5 | 80025 | st_stm32f407_datasheet_ds8626 | 25 | 33.5312 |
| 6 | 100301 | st_stm32f407_refman_rm0090 | 301 | 33.5000 |
| 7 | 80048 | st_stm32f407_datasheet_ds8626 | 48 | 33.3750 |
| 8 | 100295 | st_stm32f407_refman_rm0090 | 295 | 33.1250 |
| 9 | 70192 | st_stm32f103_refman_rm0008 | 192 | 32.7812 |
| 10 | 80050 | st_stm32f407_datasheet_ds8626 | 50 | 32.3438 |

NDCG@10: 1.0 | Recall@10: 1.0

Retrieval time: 140.9 ms

### Answer

**No, this pin combination is not supported. According to Page 2 of document RM0090, bits EXT10[3:0] and EXT2[3:0] must be set to the same value when configuring PH10 and PI10 as external interrupt sources. Setting them differently would enable PH2 instead of PI2, which is incorrect for your requirement.**

Cited pages: [100299]
Latency: 2636 ms

### Assessment

**Verdict:** incorrect

Core facts met: 0/2

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| Rejects independent PH10/PA2 routing for the stated limitation. | contradicted | [] | 0.0 |
| Explains that using PH10 requires EXTI2 and EXTI10 to select the same GPIO port. | partially_met | ['ph10', 'port'] | 0.29 |

---

## mcu-draft-006

**Question:** On an STM32F407, a DMA write to an APB1 peripheral stalls when the CPU changes the AHB/APB1 prescaler from 1 to 4 during the transfer. What causes this, how can it be prevented, and how can the MCU recover?

**Gold pages:** [{'doc_id': 'st_stm32f407_errata_es0182', 'page_number': 11, 'section': '2.2.11', 'grade': 2, 'support': 'Trigger, prevention and system-reset recovery.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 90011 | st_stm32f407_errata_es0182 | 11 | 47.6875 |
| 2 | 90013 | st_stm32f407_errata_es0182 | 13 | 45.9062 |
| 3 | 90016 | st_stm32f407_errata_es0182 | 16 | 40.9688 |
| 4 | 60024 | st_stm32f103_errata_es096 | 24 | 40.3750 |
| 5 | 90019 | st_stm32f407_errata_es0182 | 19 | 39.9688 |
| 6 | 90027 | st_stm32f407_errata_es0182 | 27 | 39.7500 |
| 7 | 50049 | st_stm32f103_datasheet_ds5319 | 49 | 39.3438 |
| 8 | 90012 | st_stm32f407_errata_es0182 | 12 | 39.1562 |
| 9 | 60016 | st_stm32f103_errata_es096 | 16 | 38.4688 |
| 10 | 20015 | espressif_esp32_errata | 15 | 38.3750 |

NDCG@10: 1.0 | Recall@10: 1.0

Retrieval time: 135.1 ms

### Answer

**[Page 1] The issue occurs due to a DMA transfer on the AHB while modifying the AHB/APB1 prescaler from 1 to 2, 1 to 4, 1 to 8 or 1 to 16. [Page 2] To prevent this, wait until the end of the DMA transfer on the affected APB before changing the prescaler. [Page 2] Recovery involves resetting through the BDRST bit or writing to the backup domain via a polling loop on targeted registers.**

Cited pages: [90011, 90013]
Latency: 1924 ms

### Assessment

**Verdict:** partial

Core facts met: 2/3

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| Identifies slowing the same APB from prescaler 1 to 4 during an active DMA write | partially_met | ['apb', 'prescaler', 'dma'] | 0.38 |
| Waits for the DMA transfer on the affected APB to finish before slowing the cloc | met | ['dma', 'transfer', 'affected', 'apb'] | 0.5 |
| Names system reset as the documented recovery. | met | ['reset', 'recovery'] | 0.5 |

---

## mcu-draft-007

**Question:** I'm migrating an STM32F407 LQFP100 board from silicon revision A to revision Z. Does the PDR_ON connection need to change, and can I continue using a 1.7 V supply?

**Gold pages:** [{'doc_id': 'st_stm32f407_errata_es0182', 'page_number': 10, 'section': '2.2.8', 'grade': 1, 'support': 'Partial answer: former PDR_ON becomes VSS and POR/PDR is always enabled; also supplies optional pin number 99.', 'evidence_type': 'text'}, {'doc_id': 'st_stm32f407_errata_es0182', 'page_number': 11, 'section': '2.2.8 continuation', 'grade': 2, 'support': 'Both migration wiring cases and enabled-POR/PDR minimum VDD of 1.8 V; sufficient for all core facts without the optional pin number.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 90011 | st_stm32f407_errata_es0182 | 11 | 39.0000 |
| 2 | 80027 | st_stm32f407_datasheet_ds8626 | 27 | 36.5312 |
| 3 | 80193 | st_stm32f407_datasheet_ds8626 | 193 | 36.4688 |
| 4 | 80026 | st_stm32f407_datasheet_ds8626 | 26 | 35.6562 |
| 5 | 80019 | st_stm32f407_datasheet_ds8626 | 19 | 35.6250 |
| 6 | 80018 | st_stm32f407_datasheet_ds8626 | 18 | 35.6250 |
| 7 | 90010 | st_stm32f407_errata_es0182 | 10 | 35.5312 |
| 8 | 80031 | st_stm32f407_datasheet_ds8626 | 31 | 35.5312 |
| 9 | 80061 | st_stm32f407_datasheet_ds8626 | 61 | 35.2188 |
| 10 | 90038 | st_stm32f407_errata_es0182 | 38 | 35.0312 |

NDCG@10: 0.8175 | Recall@10: 1.0

Retrieval time: 175.7 ms

### Answer

**According to Page 1, for applications using revision A devices with PDR_ON pin connected to VDD (POR/PDR feature enabled), you should connect the former PDR_ON pin to VSS on revision Z devices. For revision A devices with PDR_ON pin connected to VSS (POR/PDR feature disabled), no modification is required when migrating to other device revisions. However, it is no longer possible to supply the product from a 1.7 V VDD on LQFP100 package since VDD minimum value is 1.8 V when the POR/PDR feature is enabled. Therefore, you cannot continue using a 1.7 V supply; you must use a 1.8 V or higher supply voltage on the LQFP100 package.**

Cited pages: [90011]
Latency: 2575 ms

### Assessment

**Verdict:** partial

Core facts met: 2/3

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| Requires the former PDR_ON pin to be tied to VSS on revision Z: change a VDD con | met | ['former', 'pdr_on', 'pin', 'vss', 'revision', 'vdd', 'vss', 'vss'] | 0.57 |
| Explains that POR/PDR is always enabled on revision Z in LQFP100. | met | ['por/pdr', 'enabled', 'revision', 'lqfp100'] | 0.8 |
| Rejects 1.7 V operation and gives the 1.8 V minimum. | partially_met | ['minimum'] | 0.5 |

---

## mcu-draft-008

**Question:** On an STM32F407, a write to an APB peripheral register immediately after enabling its RCC clock sometimes fails. How much delay is required, and what workaround does the errata recommend?

**Gold pages:** [{'doc_id': 'st_stm32f407_errata_es0182', 'page_number': 12, 'section': '2.2.13', 'grade': 2, 'support': 'Delay rule and three workaround choices.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 90012 | st_stm32f407_errata_es0182 | 12 | 32.9375 |
| 2 | 90019 | st_stm32f407_errata_es0182 | 19 | 32.0625 |
| 3 | 90011 | st_stm32f407_errata_es0182 | 11 | 31.8125 |
| 4 | 90007 | st_stm32f407_errata_es0182 | 7 | 31.6719 |
| 5 | 90013 | st_stm32f407_errata_es0182 | 13 | 31.6094 |
| 6 | 90020 | st_stm32f407_errata_es0182 | 20 | 31.1094 |
| 7 | 90041 | st_stm32f407_errata_es0182 | 41 | 31.0781 |
| 8 | 90030 | st_stm32f407_errata_es0182 | 30 | 30.9375 |
| 9 | 90027 | st_stm32f407_errata_es0182 | 27 | 30.8906 |
| 10 | 90029 | st_stm32f407_errata_es0182 | 29 | 30.7031 |

NDCG@10: 1.0 | Recall@10: 1.0

Retrieval time: 103.5 ms

### Answer

**On an STM32F407, a write to an APB peripheral register immediately after enabling its RCC clock may fail due to a delay that depends on the peripheral mapping. The delay can be equal to 1 + (AHB/APB prescaler) cycles.

The errata recommends applying one of the following measures as a workaround:
- Use the DSB instruction to stall the Arm® Cortex®-M4 CPU pipeline until the instruction has completed.
- Insert "n" NOPs between the RCC enable bit write and the peripheral register writes (n = 2 for AHB peripherals, n = 1 + AHB/APB prescaler for APB peripherals).
- Simply insert a dummy read operation from the corresponding register just after enabling the peripheral clock. [Page 1]**

Cited pages: [90012]
Latency: 3118 ms

### Assessment

**Verdict:** correct

Core facts met: 2/2

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| Gives the delay as 1 plus the AHB/APB prescaler in CPU cycles. | met | ['delay', 'ahb/apb', 'prescaler', 'cpu', 'cycles'] | 0.83 |
| Names sufficient NOPs, DSB, or the documented post-enable dummy read as a workar | met | ['nops', 'dsb', 'dummy', 'read', 'workaround'] | 0.62 |

---

## mcu-draft-009

**Question:** On ESP32 chip revision v0.0, repeated consecutive writes to the same DPORT register address sometimes get lost, both for UART2 FIFO and for GPIO_OUT1_W1TC. What workaround should I use?

**Gold pages:** [{'doc_id': 'espressif_esp32_errata', 'page_number': 16, 'section': '3.8 / CPU-3.3 continuation', 'grade': 2, 'support': 'Prose states the mandatory AHB-alias workaround. The table addresses, FIFO-read caveat and fixed revision are optional supporting details on the same page.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 20016 | espressif_esp32_errata | 16 | 37.8125 |
| 2 | 20015 | espressif_esp32_errata | 15 | 32.6562 |
| 3 | 20024 | espressif_esp32_errata | 24 | 31.8594 |
| 4 | 20012 | espressif_esp32_errata | 12 | 31.6562 |
| 5 | 20020 | espressif_esp32_errata | 20 | 31.1562 |
| 6 | 20018 | espressif_esp32_errata | 18 | 30.6406 |
| 7 | 30150 | espressif_esp32_refman | 150 | 29.7344 |
| 8 | 20013 | espressif_esp32_errata | 13 | 29.5938 |
| 9 | 20030 | espressif_esp32_errata | 30 | 29.5781 |
| 10 | 20023 | espressif_esp32_errata | 23 | 29.5469 |

NDCG@10: 1.0 | Recall@10: 1.0

Retrieval time: 376.9 ms

### Answer

**For UART2 FIFO, use the equivalent AHB address not the DPORT address when writing the same register address in sequential instructions ([Page 1]). For GPIO_OUT1_W1TC, disable CPU interrupts before reading these five FIFO registers and enable CPU interrupts after read access ([Page 2]).**

Cited pages: [20016, 20015]
Latency: 4471 ms

### Assessment

**Verdict:** incorrect

Core facts met: 0/1

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| Uses the AHB register aliases for the affected consecutive writes. | partially_met | ['ahb', 'register'] | 0.33 |

---

## mcu-draft-010

**Question:** On ESP32 chip revision v3.1, can GPIO4 use a rising-edge interrupt while other GPIO0-31 pins also have interrupts enabled? If not, what level-triggered workaround does the errata describe?

**Gold pages:** [{'doc_id': 'espressif_esp32_errata', 'page_number': 18, 'section': '3.11 / GPIO-3.14', 'grade': 1, 'support': 'Affected revisions, group restriction and first workaround step.', 'evidence_type': 'text'}, {'doc_id': 'espressif_esp32_errata', 'page_number': 19, 'section': '3.11 continuation', 'grade': 1, 'support': 'Second rising-edge workaround step.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 20018 | espressif_esp32_errata | 18 | 38.8750 |
| 2 | 20019 | espressif_esp32_errata | 19 | 36.7500 |
| 3 | 20009 | espressif_esp32_errata | 9 | 34.7500 |
| 4 | 20016 | espressif_esp32_errata | 16 | 33.2500 |
| 5 | 30146 | espressif_esp32_refman | 146 | 33.1250 |
| 6 | 20023 | espressif_esp32_errata | 23 | 33.0000 |
| 7 | 30153 | espressif_esp32_refman | 153 | 32.9688 |
| 8 | 20017 | espressif_esp32_errata | 17 | 32.6875 |
| 9 | 10024 | espressif_esp32_datasheet | 24 | 31.9844 |
| 10 | 30142 | espressif_esp32_refman | 142 | 31.9688 |

NDCG@10: 1.0 | Recall@10: 1.0

Retrieval time: 374.3 ms

### Answer

**On ESP32 chip revision v3.1, GPIO4 cannot use a rising-edge interrupt while other GPIO0-31 pins also have interrupts enabled due to the limitation described in [GPIO-3.14] on Page 18. The errata describes a workaround: set the GPIO interrupt type to high for the desired GPIO pin before triggering the interrupt, then change it to low after the CPU services the interrupt. This ensures that the CPU ignores the interrupt service routine during the second interrupt, allowing the desired GPIO interrupt to be triggered on a rising edge.**

Cited pages: []
Latency: 2971 ms

### Assessment

**Verdict:** partial

Core facts met: 1/3

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| States the same-group edge/other-interrupt restriction. | missing | [] | 0.0 |
| Allows multiple level interrupts when no edge interrupt is configured. | partially_met | ['interrupts', 'edge', 'interrupt'] | 0.43 |
| Gives high then low triggering and ignores the second interrupt. | met | ['high', 'low', 'triggering', 'ignores', 'second', 'interrupt'] | 1.0 |

---

## mcu-draft-011

**Question:** Can ESP32 chip revision v3.1 use EXT0 wake-up together with the ULP coprocessor and touch wake-up during Deep Sleep?

**Gold pages:** [{'doc_id': 'espressif_esp32_errata', 'page_number': 17, 'section': '3.9 / ULP-3.19 continuation', 'grade': 2, 'support': 'Clock-sequencing explanation and explicit power-domain trade-off.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 20017 | espressif_esp32_errata | 17 | 30.1094 |
| 2 | 30191 | espressif_esp32_refman | 191 | 29.3750 |
| 3 | 20009 | espressif_esp32_errata | 9 | 26.6094 |
| 4 | 10031 | espressif_esp32_datasheet | 31 | 26.3281 |
| 5 | 30190 | espressif_esp32_refman | 190 | 26.1562 |
| 6 | 20016 | espressif_esp32_errata | 16 | 25.9531 |
| 7 | 30180 | espressif_esp32_refman | 180 | 25.9062 |
| 8 | 30189 | espressif_esp32_refman | 189 | 25.8438 |
| 9 | 10030 | espressif_esp32_datasheet | 30 | 25.8125 |
| 10 | 30186 | espressif_esp32_refman | 186 | 25.7344 |

NDCG@10: 1.0 | Recall@10: 1.0

Retrieval time: 128.7 ms

### Answer

**No, it cannot. According to Page 1 of the document "espressif_esp32_errata", if the RTC_PERIPH power domain is powered up, the ULP co-processor and touch sensor functionalities will not be available. This applies to revision v3.1 as indicated in Table 2.1 on Page 3.**

Cited pages: [20017, 20009]
Latency: 2152 ms

### Assessment

**Verdict:** incorrect

Core facts met: 0/2

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| Rejects simultaneous EXT0 and ULP/touch in the stated Deep-sleep setup. | missing | [] | 0.0 |
| Explains that the wake sources require incompatible RTC_PERIPH power settings. | partially_met | ['rtc_periph', 'power'] | 0.29 |

---

## mcu-draft-012

**Question:** On ESP32 revision v0.0, changing Audio PLL sdm0 and sdm1 does not provide the expected frequency precision. Is this a hardware limitation, and was it fixed in later revisions?

**Gold pages:** [{'doc_id': 'espressif_esp32_errata', 'page_number': 21, 'section': '3.16 / CLK-3.7', 'grade': 2, 'support': 'Prose identifies unused sdm0/sdm1 and the fix from chip v1.0. The rendered equation and driver discussion support optional details.', 'evidence_type': 'text'}]

### Retrieval Results

| # | Page ID | Doc ID | Page # | Score |
|---|---------|--------|--------|-------|
| 1 | 20021 | espressif_esp32_errata | 21 | 37.0625 |
| 2 | 30171 | espressif_esp32_refman | 171 | 33.3750 |
| 3 | 10077 | espressif_esp32_datasheet | 77 | 28.7812 |
| 4 | 80038 | st_stm32f407_datasheet_ds8626 | 38 | 27.8750 |
| 5 | 20023 | espressif_esp32_errata | 23 | 26.7344 |
| 6 | 10070 | espressif_esp32_datasheet | 70 | 26.5469 |
| 7 | 10011 | espressif_esp32_datasheet | 11 | 26.5000 |
| 8 | 20020 | espressif_esp32_errata | 20 | 26.3594 |
| 9 | 30170 | espressif_esp32_refman | 170 | 26.2812 |
| 10 | 20022 | espressif_esp32_errata | 22 | 26.2812 |

NDCG@10: 1.0 | Recall@10: 1.0

Retrieval time: 99.3 ms

### Answer

**Yes, it is a hardware limitation. The formula for calculating the Audio PLL frequency on chip revision v0.0 is limited by the use of configuration registers sdm0 & sdm1, which are not used when configuring the Audio PLL. This issue was fixed in chip revision v1.0, where the formula uses sdm0, sdm1, sdm2, and odiv to calculate the frequency more precisely [Page 1].**

Cited pages: [20021]
Latency: 2480 ms

### Assessment

**Verdict:** correct

Core facts met: 2/2

| Fact | Status | Key Terms Found | Term Ratio |
|------|--------|-----------------|------------|
| Identifies ignored sdm0 and sdm1 on chip v0.0. | met | ['sdm0', 'sdm1', 'chip'] | 0.75 |
| Identifies chip v1.0 as fixed. | met | ['chip', 'fixed'] | 1.0 |

---
