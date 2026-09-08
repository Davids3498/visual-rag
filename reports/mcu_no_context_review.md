# MCU no-context audit

Run: 20260908T134053918802Z

All 12 questions were approved by the user before inference. Each request contained only its question and the neutral system instruction: "Answer the question clearly and directly. If you are unsure, say so." No RAG, documents, rubrics, reference answers, tools or previous conversation were sent.

Model: Qwen/Qwen2.5-VL-7B-Instruct-AWQ (served as qwen2.5-vl-7b-awq), AWQ int4. Temperature 0, top_p 1, seed 0, maximum output 1536 tokens. All 12 responses ended normally; none was truncated. Cached model commit: 536a35794df8831aa814970ee8f89eff577e7718; this is cache evidence, not server attestation of the loaded commit. Full request and runtime metadata are in the [audit record](../corpus/questions/no_context_audits/20260908T134053918802Z.json).

## Results

0 correct, 5 partial, 5 incorrect, 2 abstained. All 12 remain eligible for the retrieval-dependent answer subset under this run. A failed response does not prove the knowledge is absent from model weights. Judgments below are by Codex (assistant), not an independent human reviewer. Only core required facts determine completeness; optional details are not required.

"Abstained" includes deferring the requested decision to documentation without giving a concrete answer. It does not imply all surrounding statements were true. "Partial" can include a correct conclusion with wrong reasoning or tentative recognition without a complete answer. These distinctions do not change which questions survive: only fully correct answers are excluded.

| Question | Verdict | Assessment |
|---|---|---|
| mcu-draft-001 | incorrect | Generic configuration advice fails both core facts; the proposed alternate-function number is not the erratum workaround. |
| mcu-draft-002 | incorrect | Refers the reader to errata and discusses generic PWM/capture uses without answering the limitation. |
| mcu-draft-003 | incorrect | Proposes disabling the watchdog and a WDCR register instead of the documented wait; claims the watchdog is inactive in Stop. |
| mcu-draft-004 | partial | Gets the general consequences but misses the specific race and documented flag-handling workaround. |
| mcu-draft-005 | partial | Correct conclusion with an incorrect general explanation about fixed EXTI mappings; does not recover the erratum-specific coupling. |
| mcu-draft-006 | partial | Prevention is correct; recovery is not. Repeating the trigger from the question is not independent evidence of prior knowledge. |
| mcu-draft-007 | abstained | Defers both requested decisions to documentation. Generic conditional advice is treated as a functional abstention, not a substantive answer. |
| mcu-draft-008 | incorrect | Claims a specific errata delay unsupported by the pinned source. No core fact is satisfied. |
| mcu-draft-009 | incorrect | Proposes delays, different registers and firmware updates without the documented workaround. Missing optional exact addresses is not the reason for failure. |
| mcu-draft-010 | partial | Recognizes the broad limitation and workaround category, but not the required workaround sequence. |
| mcu-draft-011 | abstained | Defers to documentation/support. Its statement that the interaction is not explicitly documented is contradicted by the source, but the requested technical decision is withheld. |
| mcu-draft-012 | partial | Tentatively associates later silicon including v1.0 with improvement, so receives partial recognition only. It does not distinguish a definite hardware bug from a possible software configuration issue. |

## mcu-draft-001 — incorrect

On an STM32F103C8, USART1 is clocked and PA12 is configured as an alternate-function output for USART1 RTS, but PA12 stays high. CAN is unused and its clock is disabled. What could cause this, and how can I fix it?

### Model response (verbatim)

> The issue where PA12 remains high despite being configured as an alternate-function output for USART1 RTS suggests a potential problem with the configuration or initialization of the USART1 peripheral on the STM32F103C8.
>
> Here are some steps to troubleshoot and potentially resolve the issue:
>
> 1. **Check Initialization Code**:
>    - Ensure that the USART1 initialization code correctly sets up the alternate function for PA12 (USART1 RTS).
>    - Verify that the GPIO configuration for PA12 includes the alternate function mode and the correct alternate function number (which should be 15 for USART1 RTS).
>
> 2. **Verify Clock Configuration**:
>    - Confirm that the clock for USART1 is enabled in the RCC (Register Control Clock) configuration.
>    - Ensure that the clock for PA12 is also properly configured in the GPIO clock control register.
>
> 3. **Check GPIO Configuration**:
>    - Double-check that the GPIO port A is properly configured to use alternate function mode.
>    - Ensure that the GPIO pins are not used by other peripherals that might conflict with the USART1 configuration.
>
> 4. **Debugging**:
>    - Use a debugger to step through the initialization code and verify each step.
>    - Check the state of the GPIO registers after the initialization to ensure they match your expectations.
>
> 5. **Reset and Initialization**:
>    - After making changes, reset the STM32F103C8 and reinitialize the USART1 to ensure that all configurations are applied correctly.
>
> 6. **CAN Configuration**:
>    - Since CAN is unused and its clock is disabled, ensure that no conflicting settings are inadvertently affecting the USART1 configuration.
>
> If these steps do not resolve the issue, consider checking the STM32F103C8 datasheet for any specific notes or warnings related to the USART1 and GPIO configurations. Additionally, ensure that there are no hardware issues such as broken pins or incorrect connections that might affect the functionality of the USART1.

### Core-fact assessment

- missing: Identifies the CAN/USART1_RTS conflict on PA12. Does not identify CAN_TX holding PA12 high when CAN is unclocked.
- missing: Specifies selecting the unused CAN remap when CAN is unused. Does not prescribe the unused CAN remap.

Assessment: Generic configuration advice fails both core facts; the proposed alternate-function number is not the erratum workaround.

Reference answer: The unclocked CAN alternate function can hold PA12 high. Select the unused CAN remapping, CAN_REMAP=0b01 in AFIO_MAPR bits 14:13. CAN need not be enabled merely to release USART1_RTS.

## mcu-draft-002 — incorrect

On an STM32F103x8/xB, TIM3 channel 2 on PB5 stays high with TIM3 and I2C1 both clocked and PB5 configured as an alternate-function output. SMBus Alert is unused. Why does this happen, and what use of CH2 does the errata permit in this configuration?

### Model response (verbatim)

> The behavior you're describing could be due to a few potential issues or limitations:
>
> 1. **Clock Configuration**: Ensure that the clocks for TIM3 and I2C1 are correctly enabled. The STM32F103x8/xB microcontroller requires specific clock configurations to ensure that peripherals like TIM3 and I2C1 function properly.
>
> 2. **Pin Configuration**: Verify that pin PB5 is correctly configured as an alternate-function output (AFIO) for TIM3 Channel 2. This typically involves setting the appropriate bit in the GPIO port's alternate function register (AFR).
>
> 3. **Errata Sheet**: Check the errata sheet for the STM32F103x8/xB microcontroller. Errata sheets often provide specific guidelines and limitations regarding the use of certain pins and peripherals in different configurations. They might specify that certain pins cannot be used for specific functions when other peripherals are active.
>
> 4. **Channel Use**: According to the STM32F103x8/xB datasheet, TIM3 Channel 2 (CH2) can be used for various purposes such as PWM generation, pulse counting, or as a capture/compare input/output. However, the errata sheet might have specific notes about its use in conjunction with other peripherals or under certain conditions.
>
> To resolve the issue:
> - Double-check the clock configuration.
> - Ensure that PB5 is correctly configured as AFIO for TIM3 Channel 2.
> - Refer to the errata sheet for any specific notes on the use of CH2 in your configuration.
>
> If the problem persists after these checks, it may be necessary to consult the errata sheet more closely or seek additional support from the manufacturer or community forums.

### Core-fact assessment

- missing: Explains the I2C1_SMBA conflict despite unused alert. Does not identify the I2C1_SMBA/TIM3_CH2 conflict.
- missing: Restricts CH2 to input in the stated configuration. Does not state that CH2 is restricted to input in this configuration.

Assessment: Refers the reader to errata and discusses generic PWM/capture uses without answering the limitation.

Reference answer: Partial TIM3 remap uses AFIO_MAPR.TIM3_REMAP bits 11:10=0b10, placing CH2 on PB5. With I2C1 and TIM3 clocked and PB5 configured for alternate-function output, I2C1_SMBA conflicts with TIM3_CH2 and can hold PB5 high even when SMBA is unused. ES096 permits CH2 only as an input in this configuration.

## mcu-draft-003 — incorrect

On an STM32F103x8/xB, after updating the independent watchdog settings and immediately entering Stop mode, the next watchdog update hangs and eventually resets the MCU. How can this be prevented?

### Model response (verbatim)

> The issue you're encountering with the STM32F103x8/xB microcontroller hanging on a watchdog update when entering Stop mode could be due to several factors. Here are some steps to prevent this:
>
> 1. **Check Watchdog Configuration**: Ensure that the watchdog is properly configured before entering Stop mode. The watchdog should not be enabled during Stop mode as it is not active in this state.
>
> 2. **Disable Watchdog Before Entering Stop Mode**: Before entering Stop mode, disable the watchdog timer. This can be done by setting the appropriate bits in the watchdog control register (WDCR) to disable the watchdog.
>
> 3. **Use a Different Watchdog Timer**: Consider using a different watchdog timer that is designed for use in Stop mode or ensure that the current watchdog timer is configured correctly for its intended use.
>
> 4. **Check Power Management Settings**: Ensure that the power management settings do not inadvertently enable the watchdog timer during Stop mode. Check the power management registers to ensure they are set correctly.
>
> 5. **Software Implementation**: Make sure your software implementation does not inadvertently re-enable the watchdog timer after entering Stop mode. This might happen if there is a loop or a function that re-enables the watchdog without proper checks.
>
> 6. **Hardware Reset Prevention**: If the watchdog reset is causing issues, consider implementing a hardware reset prevention mechanism. This could involve using a separate reset source that is not affected by the watchdog.
>
> 7. **Debugging**: Use debugging tools to trace the execution flow and identify where the watchdog is being re-enabled or where the reset occurs. This can help pinpoint the exact cause of the issue.
>
> By following these steps, you should be able to prevent the watchdog from hanging and resetting the MCU when entering Stop mode.

### Core-fact assessment

- missing: Waits for RVU and PVU to clear before Stop. Never says to wait for RVU and PVU to clear before Stop.
- missing: Explains that entering Stop before the watchdog update completes can leave the flags set and block later updates. Does not explain the stuck update flags and subsequent blocked writes.

Assessment: Proposes disabling the watchdog and a WDCR register instead of the documented wait; claims the watchdog is inactive in Stop.

Reference answer: Wait for both IWDG_SR.RVU (bit 1) and PVU (bit 0) to clear before entering Stop. ES096 reports that entering Stop immediately after the writes can leave these flags set and block subsequent updates. This overrides RM0008's general note that code, including low-power entry, may continue without waiting for completion.

## mcu-draft-004 — partial

On an STM32F103x8/xB, can clearing a DMA channel's global interrupt flag while the channel is active cause a transfer error to be missed or prevent automatic channel disable? How should software avoid this?

### Model response (verbatim)

> Clearing a DMA channel's global interrupt flag while the channel is active can indeed cause a transfer error to be missed because the interrupt might not be triggered in time due to the flag being cleared before the interrupt occurs. Additionally, it can prevent the automatic disabling of the channel if the interrupt is not properly handled.
>
> To avoid these issues, software should:
>
> 1. **Disable the DMA Channel Before Clearing the Interrupt Flag**: Ensure that the DMA channel is disabled before clearing its interrupt flag. This prevents the DMA from continuing operations that could lead to errors or data corruption.
>
> 2. **Properly Handle Interrupts**: Implement proper interrupt handling routines that include checking for the interrupt flag and then clearing it only after the necessary actions have been taken to handle the interrupt.
>
> 3. **Use Software Polling**: If interrupts are not used, software polling can be employed to check the status of the DMA channel periodically. This ensures that any errors or transfers are detected and handled appropriately.
>
> 4. **Error Handling Mechanisms**: Implement robust error handling mechanisms within the DMA transfer routines to detect and respond to errors as they occur.
>
> By following these guidelines, software can ensure that DMA operations are managed correctly and that any potential issues related to interrupt flags are avoided.

### Core-fact assessment

- met: States that both automatic disable and TEIFx reporting can fail. States that error reporting and automatic channel disable can fail.
- contradicted: Identifies clearing GIFx in the same clock cycle as a transfer error as the trigger. Attributes the failure to interrupt timing/handling, not a GIFx clear coinciding with a transfer error in the same clock cycle.
- partially_met: Uses specific event flags and clear bits instead of clearing active-channel GIFx. Disabling before clearing avoids an active-channel global clear, but the answer omits the required individual event flags and their clear bits.

Assessment: Gets the general consequences but misses the specific race and documented flag-handling workaround.

Reference answer: Yes. If software clears GIFx by setting CGIFx in DMA_IFCR in the same clock cycle as a transfer error, automatic channel disable fails and TEIFx is not raised. Do not clear GIFx while the channel is active; use the individual HTIFx, TCIFx and TEIFx event flags and their corresponding clear bits.

## mcu-draft-005 — partial

On an STM32F407 with PH10 available in the package, EXTI10 is mapped to PH10 while EXTI2 remains mapped to PA2, but the interrupts do not work correctly. Is this pin combination supported?

### Model response (verbatim)

> The STM32F407 series microcontroller has a specific mapping of pins to external interrupt lines (EXTI). The STM32F407 has 16 EXTI lines, which can be mapped to various GPIO pins.
>
> - **EXTI10** is typically mapped to GPIO_PIN_10 of Port H (PH10).
> - **EXTI2** is typically mapped to GPIO_PIN_2 of Port A (PA2).
>
> Given that your STM32F407 has PH10 available in the package, it means that the STM32F407 variant you have supports GPIO_PIN_10 on Port H. However, the fact that EXTI10 is mapped to PH10 and EXTI2 is mapped to PA2 suggests that the STM32F407 variant you are using might not support the combination where EXTI10 is mapped to PH10 and EXTI2 is mapped to PA2 simultaneously.
>
> The STM32F407 series does not allow for such a direct mapping of EXTI lines to different ports without additional configuration or limitations. Typically, each EXTI line is associated with a specific GPIO pin, and these associations are fixed by the STM32F407's hardware design.
>
> Therefore, the pin combination you described (EXTI10 mapped to PH10 and EXTI2 mapped to PA2) is not supported by the STM32F407 series. You would need to ensure that the EXTI lines are mapped to compatible GPIO pins according to the STM32F407's hardware specifications.

### Core-fact assessment

- met: Rejects independent PH10/PA2 routing for the stated limitation. Explicitly rejects the PH10/PA2 combination.
- missing: Explains that using PH10 requires EXTI2 and EXTI10 to select the same GPIO port. Never states that EXTI2 and EXTI10 must select the same port to use PH10.

Assessment: Correct conclusion with an incorrect general explanation about fixed EXTI mappings; does not recover the erratum-specific coupling.

Reference answer: The errata requires EXTI10 and EXTI2 to select the same port to use PH10: PH10/PH2 both select port H, encoded 0b0111. PH10 with PA2 is therefore not supported as proposed. EXTI10 is SYSCFG_EXTICR3 bits 11:8 at offset 0x10; EXTI2 is SYSCFG_EXTICR1 bits 11:8 at offset 0x08. These are offsets from SYSCFG, not absolute addresses.

## mcu-draft-006 — partial

On an STM32F407, a DMA write to an APB1 peripheral stalls when the CPU changes the AHB/APB1 prescaler from 1 to 4 during the transfer. What causes this, how can it be prevented, and how can the MCU recover?

### Model response (verbatim)

> The issue you're describing is related to the timing constraints of the STM32F407's DMA (Direct Memory Access) system when the AHB/APB1 prescaler is changed during a DMA transfer. Here’s a breakdown of what might cause the stall, how to prevent it, and how to recover:
>
> ### Causes:
> 1. **Timing Constraints**: When the AHB/APB1 prescaler is changed, the clock frequency of the peripheral changes. This change must be synchronized with the DMA transfer, which involves reading data from memory and writing it to the peripheral.
> 2. **DMA Transfer Timing**: The DMA controller needs to ensure that the data transfer happens at the correct time relative to the new clock frequency. If the transfer is not properly aligned with the new clock, it can lead to a stall.
>
> ### Prevention:
> 1. **Avoid Changing Prescaler During Transfer**: To prevent this issue, avoid changing the AHB/APB1 prescaler while a DMA transfer is in progress. Ensure that any necessary changes to the prescaler occur before the DMA transfer starts or after it has completed.
> 2. **Use Proper Synchronization**: Implement proper synchronization mechanisms within your code to ensure that the DMA transfer completes before the prescaler change occurs. This can involve checking the DMA status register to ensure the transfer is complete before making the prescaler change.
>
> ### Recovery:
> 1. **Check DMA Status**: After completing the DMA transfer, check the DMA status register to ensure the transfer is complete. If the transfer is still in progress, wait until it finishes.
> 2. **Change Prescaler Safely**: Once the DMA transfer is confirmed to be complete, safely change the prescaler. Ensure that the new prescaler value is set up correctly and that the peripheral is re-enabled if necessary.
> 3. **Monitor Clock Changes**: Monitor the clock changes closely to ensure that they do not affect ongoing operations. This might involve additional checks or delays to ensure that the new clock settings are stable before proceeding with further operations.
>
> By following these guidelines, you can prevent the DMA transfer from stalling due to changes in the prescaler, ensuring smooth operation of your STM32F407-based system.

### Core-fact assessment

- met: Identifies slowing the same APB from prescaler 1 to 4 during an active DMA write as the documented trigger. Connects the prescaler change during the active APB1 DMA write to the stall (the question already supplies this sequence).
- met: Waits for the DMA transfer on the affected APB to finish before slowing the clock. Says to wait for the DMA transfer to complete before changing the prescaler.
- contradicted: Names system reset as the documented recovery. Suggests waiting for the stalled transfer and changing the clock safely, rather than the required system reset.

Assessment: Prevention is correct; recovery is not. Repeating the trigger from the question is not independent evidence of prior knowledge.

Reference answer: ES0182 documents a blocked DMA transfer when the CPU slows the same APB during a DMA write by changing its prescaler from 1 to 2, 4, 8 or 16. Wait for DMA transfers on that APB to finish before slowing its clock. Only a system reset recovers the documented blocked-transfer condition. For the stated divide-by-four setting, RCC_CFGR.PPRE1 bits 12:10 are 0b101.

## mcu-draft-007 — abstained

I'm migrating an STM32F407 LQFP100 board from silicon revision A to revision Z. Does the PDR_ON connection need to change, and can I continue using a 1.7 V supply?

### Model response (verbatim)

> When migrating an STM32F407 LQFP100 board from silicon revision A to revision Z, it's important to check the datasheets for both revisions to ensure that the pin connections and voltage requirements remain compatible.
>
> For the PDR_ON (Power Disable On) connection:
> - Check the datasheet of revision A to see where this pin is connected.
> - Check the datasheet of revision Z to see if the pin connection has changed.
> - If the pin connection has not changed, you can continue using the same connection.
> - If the pin connection has changed, you will need to update your design accordingly.
>
> Regarding the supply voltage:
> - Ensure that the minimum and maximum operating voltages specified in the datasheet of revision Z are within the range of 1.7V.
> - If the minimum or maximum operating voltage of revision Z falls outside the 1.7V range, you may need to adjust your power supply to meet the new specifications.
>
> It's recommended to consult the specific datasheets for revisions A and Z to confirm these details before making any changes to your design.

### Core-fact assessment

- missing: Requires the former PDR_ON pin to be tied to VSS on revision Z: change a VDD connection to VSS, or retain an existing VSS connection. Defers checking the pin connection to datasheets; gives no VSS requirement or concrete migration cases.
- missing: Explains that POR/PDR is always enabled on revision Z in LQFP100. Does not state that POR/PDR is always enabled on revision Z.
- missing: Rejects 1.7 V operation and gives the 1.8 V minimum. Gives no rejection of 1.7 V and no 1.8 V minimum.

Assessment: Defers both requested decisions to documentation. Generic conditional advice is treated as a functional abstention, not a substantive answer.

Reference answer: On revision Z, the former PDR_ON pin (pin 99) is VSS and must be tied to VSS. If it was tied to VDD on revision A, change that connection to VSS; if it was already tied to VSS, no wiring change is needed. POR/PDR is always enabled on revision Z in LQFP100, so 1.7 V operation is no longer supported; the minimum VDD is 1.8 V.

## mcu-draft-008 — incorrect

On an STM32F407, a write to an APB peripheral register immediately after enabling its RCC clock sometimes fails. How much delay is required, and what workaround does the errata recommend?

### Model response (verbatim)

> The STM32F407 series microcontroller has a specific errata that recommends a minimum delay of 100 nanoseconds (ns) between enabling the clock for an APB peripheral and writing to its register. This delay ensures that the peripheral's registers are fully initialized before any writes are attempted.
>
> The errata also suggests using a software delay function or a timer interrupt to ensure this minimum delay is respected. Here’s a simple example in C code:
>
> ```c
> #include <stm32f4xx_hal.h>
>
> void Delay(uint32_t nsec)
> {
>     HAL_Delay(nsec);
> }
>
> // Example usage:
> HAL_RCC_OscConfig(&RCC_OscInitStruct); // Enable the clock
> HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4); // Configure the clock
>
> // Wait for at least 100 ns
> Delay(100); // Adjust the value based on your system's requirements
> ```
>
> This code snippet demonstrates how to configure the clock and then wait for a minimum delay before attempting to write to the APB peripheral register. Adjust the `Delay` function call as necessary based on your specific timing requirements.

### Core-fact assessment

- contradicted: Gives the delay as 1 plus the AHB/APB prescaler in CPU cycles. Invents a fixed 100 ns delay instead of 1 + AHB/APB prescaler cycles.
- missing: Names sufficient NOPs, DSB, or the documented post-enable dummy read as a workaround. Omits the documented NOP count, DSB and post-enable dummy read; substitutes unrelated delay code.

Assessment: Claims a specific errata delay unsupported by the pinned source. No core fact is satisfied.

Reference answer: For an APB peripheral, allow the documented delay of 1 + (AHB/APB prescaler) cycles after enabling its RCC clock. The errata permits inserting that number of NOPs, using DSB, or inserting a dummy read from the corresponding register just after clock enable. Five NOPs is the example for a prescaler of 4, not a universal delay.

## mcu-draft-009 — incorrect

On ESP32 chip revision v0.0, repeated consecutive writes to the same DPORT register address sometimes get lost, both for UART2 FIFO and for GPIO_OUT1_W1TC. What workaround should I use?

### Model response (verbatim)

> For the ESP32 chip revision v0.0, when you encounter issues with repeated consecutive writes to the same DPORT register address getting lost, especially for UART2 FIFO and GPIO_OUT1_W1TC, you can try the following workarounds:
>
> 1. **Use Delay Between Writes**: Introduce a small delay (e.g., 1-5 microseconds) between consecutive writes to the same register. This can help ensure that the write operation completes before the next one starts.
>
> 2. **Check Register Address Consistency**: Ensure that the register addresses you are writing to are correct and consistent across multiple operations. Sometimes, incorrect register addresses can lead to unexpected behavior.
>
> 3. **Use Different Registers**: If possible, use different registers for consecutive writes. This can help avoid conflicts in the write operations.
>
> 4. **Check for Hardware Limitations**: Verify if there are any hardware limitations or design flaws specific to the ESP32 v0.0 revision that might be causing this issue. Sometimes, hardware revisions can introduce such limitations.
>
> 5. **Update Firmware**: Consider updating the firmware of your ESP32 to a more recent version. Newer versions often include bug fixes and improvements that could resolve this issue.
>
> 6. **Use Interrupts**: Implementing an interrupt-driven approach where you wait for the interrupt to clear after each write can also help manage the timing of the writes more effectively.
>
> 7. **Check for Interference**: Ensure that there is no interference from other components or signals that might be affecting the write operations.
>
> By implementing these strategies, you should be able to mitigate the issue of repeated consecutive writes getting lost on the ESP32 chip revision v0.0.

### Core-fact assessment

- missing: Uses the AHB register aliases for the affected consecutive writes. Never recommends the equivalent AHB register aliases.

Assessment: Proposes delays, different registers and firmware updates without the documented workaround. Missing optional exact addresses is not the reason for failure.

Reference answer: Use the AHB aliases 0x6002E000 for UART2_FIFO_REG and 0x60004018 for GPIO_OUT1_W1TC_REG. Software must not use the AHB addresses to read a FIFO. The repeated-write issue was fixed in chip revision v1.0.

## mcu-draft-010 — partial

On ESP32 chip revision v3.1, can GPIO4 use a rising-edge interrupt while other GPIO0-31 pins also have interrupts enabled? If not, what level-triggered workaround does the errata describe?

### Model response (verbatim)

> The ESP32 chip revision v3.1 has a known limitation where GPIO4 cannot be used for rising-edge interrupts if other GPIO0-31 pins also have interrupts enabled. This is due to an erratum in the datasheet that describes this specific issue.
>
> To work around this limitation, the erratum suggests using GPIO4 as a level-triggered input instead of a rising-edge interrupt. This means that instead of setting up a rising-edge interrupt on GPIO4, you would set it up as a level-triggered interrupt. This workaround allows GPIO4 to function correctly with other GPIO interrupts enabled without causing conflicts.

### Core-fact assessment

- met: States the same-group edge/other-interrupt restriction. States the GPIO4 rising-edge versus other GPIO0-31 interrupt restriction.
- partially_met: Allows multiple level interrupts when no edge interrupt is configured. Says level triggering can coexist with other interrupts, but omits that no edge-triggered interrupt may remain in the group.
- partially_met: Gives high then low triggering and ignores the second interrupt. Recommends level triggering but omits high-then-low switching and ignoring the second interrupt.

Assessment: Recognizes the broad limitation and workaround category, but not the required workaround sequence.

Reference answer: If one pin in the group uses an edge-triggered interrupt, the errata disallows configuring other interrupts in the same group. With no edge-triggered interrupts, multiple level-triggered interrupts are allowed. Emulate rising-edge detection by selecting high-level triggering, then changing to low-level triggering after servicing; ignore the second interrupt described by the workaround.

## mcu-draft-011 — abstained

Can ESP32 chip revision v3.1 use EXT0 wake-up together with the ULP coprocessor and touch wake-up during Deep Sleep?

### Model response (verbatim)

> The ESP32 chip revision v3.1 supports the use of the ULP (Ultra Low Power) coprocessor for various low-power modes, including Deep Sleep. However, the functionality of the ULP coprocessor in conjunction with the EXT0 wake-up and touch wake-up during Deep Sleep is not explicitly detailed in the datasheet or official documentation.
>
> The ESP32's Deep Sleep mode is designed to be very power-efficient, but it does not provide detailed information on how specific wake-up methods interact with the ULP coprocessor in this state. For precise operation, it would be advisable to refer to the latest ESP32 datasheet or consult with the manufacturer's technical support for clarification on the specific capabilities and limitations of these features in revision v3.1.

### Core-fact assessment

- missing: Rejects simultaneous EXT0 and ULP/touch in the stated Deep-sleep setup. Does not decide that EXT0 with ULP/touch is unsupported.
- missing: Explains that the wake sources require incompatible RTC_PERIPH power settings. Does not identify incompatible RTC_PERIPH power settings.

Assessment: Defers to documentation/support. Its statement that the interaction is not explicitly documented is contradicted by the source, but the requested technical decision is withheld.

Reference answer: The documented combination is not supported. EXT0 requires RTC_PERIPH powered up, but the errata requires it powered down in Deep-sleep to use the ULP coprocessor and touch sensors because of their wake-up clock sequencing. Choose EXT0 with the domain powered up, or ULP/touch with it powered down and EXT0 unavailable.

## mcu-draft-012 — partial

On ESP32 revision v0.0, changing Audio PLL sdm0 and sdm1 does not provide the expected frequency precision. Is this a hardware limitation, and was it fixed in later revisions?

### Model response (verbatim)

> The issue you're describing with the ESP32's Audio PLL (Phase-Locked Loop) on revision v0.0 might be due to a hardware limitation or a software configuration issue that wasn't fully resolved until later revisions of the ESP32.
>
> In the early stages of development for the ESP32, the Audio PLL's performance could vary depending on the specific hardware revision and the firmware version used. The SDM0 and SDM1 settings are part of the PLL configuration, which can affect the output frequency stability and precision.
>
> Later revisions of the ESP32, such as v1.0 and onwards, have seen improvements in the PLL's performance and stability. These revisions likely address the hardware limitations and improve the consistency of the audio output frequency across different boards.
>
> It is recommended to use the latest firmware and hardware revisions when working with the ESP32 to ensure optimal performance and reliability. Always refer to the official documentation and community forums for the most up-to-date information and best practices.

### Core-fact assessment

- missing: Identifies ignored sdm0 and sdm1 on chip v0.0. Does not state that sdm0 and sdm1 are ignored on chip v0.0.
- partially_met: Identifies chip v1.0 as fixed. Mentions v1.0 onwards as likely improving the PLL, but does not establish that the specific bug was fixed then.

Assessment: Tentatively associates later silicon including v1.0 with improvement, so receives partial recognition only. It does not distinguish a definite hardware bug from a possible software configuration issue.

Reference answer: Revision v0.0 ignores sdm0 and sdm1: fout = fxtal * (sdm2 + 4) / (2 * (odiv + 2)). The bug is fixed from chip revision v1.0. ESP-IDF v3.0 and newer I2S drivers account for the old calculation but cannot remove v0.0's frequency range and precision limits.
